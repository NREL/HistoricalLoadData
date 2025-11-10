import pandas as pd
import os
os.environ['USE_PYGEOS'] = '0'
import geopandas as gpd
import requests
import datetime

def remove_points_and_lines(df, dissolve_cols=None):
    df = df.explode()
    if dissolve_cols:
        df = (
            df.loc[~df.geometry.type.isin(['Point', 'LineString'])]
            .dissolve(dissolve_cols)
            .reset_index()
        )
    else:
        df = (
            df.loc[~df.geometry.type.isin(['Point', 'LineString'])]
            .dissolve()
            .reset_index()
        )

    return df

def calculate_intersection(df1, df2, dissolve_cols):
    df_intersect = gpd.overlay(
        df1,
        df2,
        how='intersection',
        keep_geom_type=False
    )
    df_intersect = remove_points_and_lines(df_intersect, dissolve_cols)

    return df_intersect

def add_short_form_data(bulk_power_sales, load_year):
    short_form = pd.read_excel(f"../data/sales/Short_Form_{load_year}.xlsx")
    if load_year == 2016:
        short_form = short_form.rename(columns={"BA_CODE": "BA Code"})
    
    short_form = (
        short_form[['Utility Number', 'Utility Name', 'State', 'BA Code', 'Total Sales (MWh)', 'Total Customers']]
        .rename(columns={"Total Sales (MWh)": "Megawatthours", "Total Customers": "Count"})
    )
    short_form = (
        short_form.loc[~short_form['State'].isin(['HI', 'AK'])]
        .dropna(how='all')
    )
    short_form['Megawatthours'] = (
        pd.to_numeric(short_form.Megawatthours, errors='coerce')
        .astype(float)
        .fillna(0)
    )
    short_form_sales = (
        short_form.groupby(['State', 'BA Code'], dropna=False)
        .Megawatthours
        .sum()
    )

    # Remove short form sales from the adjustment entry
    adjustment_entry = f"Adjustment {load_year}"
    initial_total_sales = bulk_power_sales.Megawatthours.sum()
    for (state, ba_code), sales_mwh in short_form_sales.items():
        if pd.isna(ba_code):
            adjust_mask = (
                (bulk_power_sales.State == state)
                & (bulk_power_sales['BA Code'].isna())
                & (bulk_power_sales['Utility Name'] == adjustment_entry)
            )
        else:
            adjust_mask = (
                (bulk_power_sales.State == state)
                & (bulk_power_sales['BA Code'] == ba_code)
                & (bulk_power_sales['Utility Name'] == adjustment_entry)
            )
    
        bulk_power_sales.loc[adjust_mask, 'Megawatthours'] -= sales_mwh

    bulk_power_sales = pd.concat([bulk_power_sales, short_form])
    assert round(bulk_power_sales.Megawatthours.sum()) == round(initial_total_sales)

    return bulk_power_sales

def get_plant_direct_use(load_year):
    if load_year == 2023:
        fpath = "../data/sales/EIA923_Schedules_6_7_NU_SourceNDisposition_2023_Final.xlsx"
    else:
        fpath = f"../data/sales/EIA923_Schedules_6_7_NU_SourceNDisposition_{load_year}_Final_Revision.xlsx"
    plant_direct_use = pd.read_excel(fpath)
    plant_direct_use.columns = [
        col.replace('\n', ' ').replace('  ', ' ').replace(' ', '_')
        for col in plant_direct_use.loc[3]
    ]
    plant_direct_use = plant_direct_use.loc[4:]
    plant_direct_use = plant_direct_use.rename(columns={
        "Utility_ID": "Utility Number",
        "Plant_Code": "Plant Code",
        "Gross_Generation": "gross_generation_mwh",
        "Direct_Use": "direct_use_mwh"
    })
    for col in ["gross_generation_mwh", "direct_use_mwh"]:
        plant_direct_use[col] = (
            pd.to_numeric(plant_direct_use[col], errors='coerce')
            .astype(float)
            .fillna(0)
        )

    # Only consider direct use of self-generated electricity, as direct use
    # of incoming electricity is already accounted for in sales
    plant_direct_use["direct_use_mwh"] = (
        plant_direct_use[["gross_generation_mwh", "direct_use_mwh"]].min(axis=1)
    )
    plant_direct_use = plant_direct_use[["Plant Code", "Utility Number", "direct_use_mwh"]]

    return plant_direct_use

def get_plant_prime_movers(load_year):
    def clean_raw_data(df):
        df.columns = [col.replace('\n', ' ') for col in df.loc[4]]
        df = (
            df[5:]
            .rename(columns={
                "Plant Id": "Plant Code",
                "Balancing Authority Code": "BA Code",
                "Reported Prime Mover": "prime_mover",
                "Net Generation (Megawatthours)": "net_generation_mwh"
            })
        )
        df['net_generation_mwh'] = (
            pd.to_numeric(df['net_generation_mwh'], errors='coerce')
            .astype(float)
            .fillna(0)
        )
        return df

    if load_year == 2023:
        fpath = "../data/sales/EIA923_Schedules_2_3_4_5_M_12_2023_Final.xlsx"
    else:
        fpath = f"../data/sales/EIA923_Schedules_2_3_4_5_M_12_{load_year}_Final_Revision.xlsx"

    plant_prime_movers = pd.read_excel(fpath)
    plant_prime_movers = clean_raw_data(plant_prime_movers)

    if load_year < 2018:
        # There are no BA codes listed for 2016-2017, so get them from 2018 plant dataset
        plant_prime_movers_2018 = pd.read_excel(
            "../data/sales/EIA923_Schedules_2_3_4_5_M_12_2018_Final_Revision.xlsx"
        )
        plant_prime_movers_2018 = clean_raw_data(plant_prime_movers_2018)
        original_length = len(plant_prime_movers)
        plant_prime_movers = (
            plant_prime_movers.merge(
                plant_prime_movers_2018[['Plant Code', 'BA Code']].drop_duplicates(),
                on="Plant Code",
                how="left"
            )
        )
        assert len(plant_prime_movers) == original_length

    plant_prime_movers = (
        plant_prime_movers.groupby(['Plant Code', 'BA Code', 'prime_mover'])
        .sum(numeric_only=True)
        .reset_index()
    )
    plant_prime_movers.loc[plant_prime_movers.net_generation_mwh < 0, 'net_generation_mwh'] = 0    
    plant_prime_movers['percent_of_net_generation'] = (
        plant_prime_movers.groupby(['Plant Code', 'BA Code'])
        ['net_generation_mwh']
        .transform(
            lambda x: 1 / len(x)
            if x.sum() == 0
            else x / x.sum()
        )
    )
    plant_prime_movers = plant_prime_movers.drop(columns='net_generation_mwh')

    return plant_prime_movers

def clean_sales_data(df, load_year):
    if (load_year == 2019) and ("Unnamed: 24" in df.columns):
        df = df[[
            "Unnamed: 1", "Unnamed: 2", "Unnamed: 3", "Unnamed: 4",
            "Unnamed: 6", "Unnamed: 8", "Unnamed: 23", "Unnamed: 24",
            "Unnamed: 7"
        ]]
    else:
        df = df[[
            "Unnamed: 1", "Unnamed: 2", "Unnamed: 3", "Unnamed: 4",
            "Unnamed: 6", "Unnamed: 8", "Unnamed: 22", "Unnamed: 23",
            "Unnamed: 7"
        ]]
    df.columns = df.loc[1]
    if load_year == 2016:
        df = df.rename(columns={"BA_CODE": "BA Code"})
    df = df.loc[2:].reset_index(drop=True)
    df['Megawatthours'] = (
        pd.to_numeric(df.Megawatthours, errors='coerce')
        .astype(float)
    )
    df['Count'] = (
        pd.to_numeric(df['Count'], errors='coerce')
        .astype(float)
    )
    df = df.dropna(how='all')

    return df

def add_texas_delivery_sales(sales_ult_cust, load_year):
    if load_year < 2020:
        tx_delivery_sales = pd.read_excel("../data/sales/Delivery_Companies_2020.xlsx")
        tx_delivery_sales = clean_sales_data(tx_delivery_sales, 2020)
        tx_delivery_sales_mwh = tx_delivery_sales.Megawatthours.sum()

        sales_ult_cust_2020 = pd.read_excel("../data/sales/Sales_Ult_Cust_2020.xlsx")
        sales_ult_cust_2020 = clean_sales_data(sales_ult_cust_2020, load_year)
        tx_erco_2020_sales_mwh = (
            sales_ult_cust_2020.loc[
                (sales_ult_cust_2020.State == 'TX')
                & (sales_ult_cust_2020['BA Code'] == 'ERCO')
            ].Megawatthours.sum()
        )

        tx_delivery_sales_proportion = tx_delivery_sales_mwh / tx_erco_2020_sales_mwh
        tx_erco_sales_mwh = (
            sales_ult_cust.loc[
                (sales_ult_cust.State == 'TX') & (sales_ult_cust['BA Code'] == 'ERCO')
            ].Megawatthours.sum()
        )
        tx_delivery_sales['Megawatthours'] = (
            tx_delivery_sales['Megawatthours'] 
            / tx_delivery_sales_mwh 
            * tx_erco_sales_mwh 
            * tx_delivery_sales_proportion
        )
    else:
        tx_delivery_sales = pd.read_excel(f"../data/sales/Delivery_Companies_{load_year}.xlsx")
        tx_delivery_sales = clean_sales_data(tx_delivery_sales, load_year)

    part_d_sales_mwh = sales_ult_cust.loc[sales_ult_cust.Part == 'D']['Megawatthours'].sum()
    tx_delivery_sales_mwh = tx_delivery_sales['Megawatthours'].sum()
    tx_delivery_sales_adjustment_mwh = tx_delivery_sales_mwh - part_d_sales_mwh

    # Replace part D sales with TX/ERCO delivery sales
    sales_ult_cust = pd.concat([
        (
            sales_ult_cust.loc[sales_ult_cust['Part'] != 'D']
            .copy()
            .reset_index(drop=True)
        ),
        tx_delivery_sales
    ])

    # TX/ERCO delivery sales are higher than the Part D sales, so subtract the surplus
    # from the TX/ERCO adjustment entry
    adjustment_entry = f"Adjustment {load_year}"
    adjust_mask = (
        (sales_ult_cust.State == 'TX')
        & (sales_ult_cust['BA Code'] == 'ERCO')
        & (sales_ult_cust['Utility Name'] == adjustment_entry)
    )
    sales_ult_cust.loc[adjust_mask, 'Megawatthours'] -= tx_delivery_sales_adjustment_mwh

    assert all(sales_ult_cust.loc[adjust_mask, 'Megawatthours'] >= 0)
    
    return sales_ult_cust

def get_bulk_power_sales(load_year, utility_id_updates=None):
    sales_ult_cust = pd.read_excel(f"../data/sales/Sales_Ult_Cust_{load_year}.xlsx")
    sales_ult_cust = clean_sales_data(sales_ult_cust, load_year)
    sales_ult_cust = add_texas_delivery_sales(sales_ult_cust, load_year)
    bulk_power_sales = (
        sales_ult_cust.loc[(
            (~sales_ult_cust['State'].isin(['HI', 'AK']))
            & (sales_ult_cust["Ownership"] != "Behind the Meter")
            & (sales_ult_cust['Service Type'] != 'Energy')
        )]
        .dropna(how='all')
    )
    bulk_power_sales = (
        bulk_power_sales.groupby(
            ['Utility Number', 'Utility Name', 'State', 'BA Code'],
            dropna=False
        )
        .sum(numeric_only=True)
        .reset_index()
    )
    if load_year != 2019:
        bulk_power_sales = add_short_form_data(bulk_power_sales, load_year)
    bulk_power_sales['eia_code'] = bulk_power_sales['BA Code']
    bulk_power_sales['Utility Number'] = (
        bulk_power_sales['Utility Number'].astype(int).astype(str)
    )
    bulk_power_sales['state_utility'] = (
        bulk_power_sales['State'] + '_' + bulk_power_sales['Utility Number']
    )

    if utility_id_updates:
        bulk_power_sales['Utility Number'] = bulk_power_sales['Utility Number'].apply(
            lambda x: utility_id_updates.get(x, x)
        )
        bulk_power_sales['Utility Number'] = bulk_power_sales.apply(
            axis=1, func=lambda x: utility_id_updates.get(x['state_utility'], x['Utility Number'])
        )
    bulk_power_sales['Utility Number'] = bulk_power_sales['Utility Number'].astype(int)
    
    bulk_power_sales['state_utility'] = (
        bulk_power_sales['State'] + '_' + bulk_power_sales['Utility Number'].astype(str)
    )

    return bulk_power_sales

def get_service_territories(county2zone, load_year):
    service_territories = pd.read_excel(f"../data/sales/Service_Territory_{load_year}.xlsx")

    reeds_states = list(county2zone.state.unique())
    service_territories = (
        service_territories.loc[service_territories.State.isin(reeds_states)]
        .copy()
        .reset_index(drop=True)
    )

    city_counties = list(county2zone.loc[county2zone.county_name.str.contains("city")].county_name)
    service_territories['county_lower'] = (
        service_territories['County'].str.lower()
        .str.replace(r'\bst ', 'st. ', regex=True)
        .str.replace(r'\bste ', 'ste. ', regex=True)
        .apply(lambda x: x if x in city_counties else x.replace(' city', ''))
    )
    # These counties need to be renamed manually to match ReEDS county names
    rename_county_state_map = {
        ('prince georges', 'MD'): ("prince george's", "MD"),
        ('desoto', 'LA'): ('de soto', 'LA'),
        ('queen annes', 'MD'): ("queen anne's", 'MD'),
        ('lasalle', 'IL'): ('la salle', 'IL'),
        ('dewitt', 'IL'): ('de witt', 'IL'),
        ('st.  helena', 'LA'): ("st. helena", "LA"),
        ('miami dade', 'FL'): ('miami-dade', 'FL'),
        ('carson', 'NV'): ('carson city', 'NV'),
        ('st. marys', 'MD'): ("st. mary's", "MD"),
        ('charles', 'VA'): ('charles city', 'VA'),
        ('james', 'VA'): ('james city', 'VA'),
        ('shannon', 'SD'): ('oglala lakota', 'SD'),
    }
    service_territories['county_state'] = (
        pd.Series(list(zip(service_territories['county_lower'], service_territories['State'])))
        .apply(lambda x: rename_county_state_map.get(x, x))
    )
    service_territories = (
        service_territories.drop_duplicates(['Utility Number', 'county_state'])
        .reset_index(drop=True)
    )
    service_territories['state_utility'] = (
        service_territories['State'] + '_' + service_territories['Utility Number'].astype(str)
    )

    return service_territories

def get_county2zone(load_year):
    county_populations = (
        pd.read_csv(
            "../data/population/processed/county_populations_by_year.csv",
            usecols=['FIPS', str(load_year)]
        )
        .rename(columns={str(load_year): 'population'})
    )
    county2zone = pd.read_csv("../data/county2zone.csv")
    county2zone.loc[county2zone.county_name == 'district of columbia', 'state'] = 'DC'
    county2zone['FIPS'] = 'p' + county2zone['FIPS'].astype(str).str.zfill(5)
    county2zone['county_state'] = list(zip(county2zone['county_name'], county2zone['state']))
    county2zone = county2zone.merge(county_populations, on='FIPS', how='left')

    return county2zone

def get_dst_timestamps(year):
    url = f"https://aa.usno.navy.mil/api/daylightsaving?year={year}"
    response = requests.get(url)
    resp_data = response.json()['data']
    start_ts, end_ts = [
        datetime.datetime(date_info['year'], date_info['month'], date_info['day'], 2, 0, 0)
        for date_info in resp_data
    ]
    assert start_ts < end_ts
    return start_ts, end_ts

def get_baseline_load_profiles():
    baseline_load_profiles = {}
    hourly_demand_path = "../data/baseline_load_profiles/processed"
    for fname in os.listdir(hourly_demand_path):
        fpath = os.path.join(hourly_demand_path, fname)
        if os.path.isdir(fpath):
            continue
        df = pd.read_csv(fpath, parse_dates=["timestamp"], index_col="timestamp")
        eia_code = fname.replace('.csv', '')
        baseline_load_profiles[eia_code] = (
            df.loc[(df.index.year <= 2023) & (df.index.year >= 2016)]
            ['value']
        )

    return baseline_load_profiles

def get_rooftop_pv_cf_profiles_by_sector():
    rooftop_pv_cf_profiles_by_sector = {}
    for sector in ['residential', 'commercial']:
        df_list = []

        for year in range(2016, 2024):
            df_cf = pd.read_hdf(f'../data/distpv_profiles/{sector}_{year}.h5')
            df_list.append(df_cf)

        df_cf = pd.concat(df_list)
        del df_list
        rooftop_pv_cf_profiles_by_sector[sector] = df_cf
    
    return rooftop_pv_cf_profiles_by_sector

def rescale_profile(profile, annual_totals):
    profile_norm = profile.apply(lambda x: x / x.groupby(x.index.year).transform('sum'))
    profile_norm = profile_norm.set_index(profile_norm.index.year, append=True)
    rescaled_profile = (
        profile_norm.mul(annual_totals.T, level=1)
        .fillna(0)
        .droplevel(1)
    )

    return rescaled_profile