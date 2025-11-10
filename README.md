# Setup
1) Create the conda environment by running `conda env create -f environment.yml`.
2) Activate the conda environment by running `conda activate hld`.
3) Register an ipykernel for the environment by running `python -m ipykernel install --user --name hld --display-name "Python (hld)"`
4) Run `jupyter notebook` to start running the notebooks.

To recreate the county-level load profiles using the data files here, the only notebook that needs to be run is the `load_scaling/create_county_load_profiles.ipynb`. The county-level load profiles can be downloaded directly from https://data.openei.org/submissions/8562. The Python package `pandas` can be used to open the `.h5` file, as shown below. 

```python
import pandas as pd

df = pd.read_hdf("historic_load_hourly_2016_2023_county.h5")
```

A description of the broader pipeline is presented below.

`load_data_collection` collects and/or pre-processes hourly BA/sub-BA load and load forecast data from EIA-930 or from RTO-specific websites/APIs. Note that some scripts require you to register for your own API key.

`load_data_processing` does further processing on the hourly BA/sub-BA load and load forecast data and combines them to create the full set of baseline load profiles (`data/baseline_load_profiles`) used in subsequent processes.

`eia_data_cleaner` imputes the hourly BA/sub-BA load and load forecast data using the MICE imputation technique described in https://www.nature.com/articles/s41597-020-0483-x. Note that step 1 of this process (`step1_get_eia_demand_data.ipynb`) is not relevant to this repo since we get the data already in `load_data_collection`. The notebooks/programs should be run in the following order:
1) `step2_anomaly_screening.ipynb`
2) `MICE_step.Rmd`
3) `step4_distribute_MICE_results.ipynb`
The folder also contains the outputs of the MICE technique for each profile type (`eia_data_cleaner/data/{forecast|load_loss_correction|regional|subregional}/outputs`).

`load_loss_correction` adjusts the hourly BA/sub-BA load profiles to add load during periods of reported load loss. The notebooks should be run in the following order:
1) `create_ba_subba_shapefile.ipynb`
2) `create_county_subba_map.ipynb`
3) `calculate_ba_utility_timezones.ipynb`
4) `create_load_loss_events_database.ipynb`
5) `apply_load_loss_correction.ipynb`

`load_scaling` estimates annual county-level retail sales, calculates annual county-level direct use, estimates annual county-level on-site consumption of distributed photovoltaic (DPV)-generated electricity, estimates the percentage of county load served by each BA/sub-BA for each county, and rescales/combines the hourly BA/sub-BA load profiles to create hourly county-level retail sales and direct use profiles.
It also rescales/combines hourly county-level DPV capacity factor profiles to create hourly county-level DPV consumption profiles and adds these to the hourly county-level retail sales and direct use profiles to create the final hourly county-level load profiles. The notebooks should be run in the following order:
1) `calculate_county_retail_sales.ipynb`
2) `power_plant_counties.ipynb`
3) `calculate_county_direct_use.ipynb`
4) `calculate_county_distpv_consumption.ipynb`
5) `calculate_county_zone_area_coverage.ipynb`
6) `create_county_load_profiles.ipynb`

`validation` compares the 2023 county-level load estimates for California's counties to 2023 annual county-level consumption data published by the California Energy Commission and the 2023 hourly state-level load profile for California published in EIA-930.

Note that the following data files had to be compressed to comply with Github file size limits and therefore need to be unzipped/extracted before running notebooks that depend on these files:
- `data/distpv_profiles/{residential|commercial}_{2016|2017|2018|2019|2020|2021|2022|2023}.zip`
- `data/shapefiles/US_COUNTY_2022.7z`
- `data/eia_load_profiles/raw/EBA-pre2019.7z`
