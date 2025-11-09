`load_data_collection` collects and/or pre-processes hourly BA/sub-BA load and load forecast data from EIA-930 or from RTO-specific websites/APIs.

`load_data_processing` does further processing on the hourly BA/sub-BA load and load forecast data and combines them.

`eia_data_cleaner` imputes the hourly BA/sub-BA load and load forecast data using the MICE imputation technique described in https://www.nature.com/articles/s41597-020-0483-x. It also contains the outputs of the technique and the outputs of the load loss correction process (see `load_loss_correction`).

`load_loss_correction` adjusts the hourly BA/sub-BA load profiles to add load during periods of reported load loss.

`load_scaling` estimates annual county-level retail sales, calculates annual county-level direct use, estimates annual county-level on-site consumption of distributed photovoltaic (DPV)-generated electricity, estimates the percentage of county load served by each BA/sub-BA for each county, and rescales/combines the hourly BA/sub-BA load profiles to create hourly county-level retail sales and direct use profiles.
It also rescales/combines hourly county-level DPV capacity factor profiles to create hourly county-level DPV consumption profiles and adds these to the hourly county-level retail sales and direct use profiles to create the final hourly county-level load profiles.

`validation` compares the 2023 county-level load estimates for California's counties to 2023 annual county-level consumption data published by the California Energy Commission and the 2023 hourly state-level load profile for California published in EIA-930.
