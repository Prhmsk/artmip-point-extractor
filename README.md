# ARTMIP Point Extractor

A Streamlit application for extracting location-based atmospheric-river activity from ARTMIP binary tag catalogues.

## What it does

The app accepts a latitude, longitude, spatial buffer, ARTMIP method/dataset, year range, and processing parameters. It then:

1. Downloads the annual ARTMIP NetCDF catalogue files from NSF NCAR GDEX.
2. Uses a compact regional window around the requested location rather than loading the full global grid into memory.
3. Finds connected binary AR components intersecting the user-defined buffer.
4. Produces a time-step catalogue, daily activity catalogue, and post-processed event catalogue.
5. Exports the result as an Excel workbook plus CSV files.

The current release exposes **Guan & Waliser — ERA5 Tier-2**. More ARTMIP methods can be added through the `DATASETS` registry in `src/artmip_point_extractor/catalogue.py`.

## Important scientific interpretation

The event catalogue is constructed after spatially restricting the binary AR tags to components intersecting the user-defined buffer. Therefore, event IDs are **post-processed location-specific episodes**, not native ARTMIP track IDs.

The app extracts ARTMIP binary tags. IVT statistics are intentionally not required for the core workflow. A later release can add optional ERA5 IVT enrichment without making the ARTMIP extraction dependent on a local IVT archive.

## Data source

NSF NCAR GDEX: **Atmospheric River Tracking Method Intercomparison Project Tier 2 Reanalysis Source Data and Catalogues**, dataset d651018, DOI `10.26024/RAWV-YX53`.

GDEX currently describes hourly ERA5 binary AR tags for January 2000 through December 2019 for submitted Tier-2 developer catalogues.

## Local installation

```bash
git clone https://github.com/YOUR-USERNAME/artmip-point-extractor.git
cd artmip-point-extractor
python -m venv .venv

# Windows
.venv\\Scripts\\activate

# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## GitHub / Streamlit Community Cloud

The repository can be deployed to Streamlit Community Cloud using `app.py` as the entry point. The application does not require secrets for the public GDEX download endpoints used here.

Because annual NetCDF files can be large, the application stores them in a local `.artmip_cache` directory in the runtime environment. The cache is intentionally excluded from Git.

## Output workbook

The Excel file contains:

- `Metadata` — coordinates, buffer, dataset, years, parameters, source, and summary information
- `6-hourly` — extracted AR activity at the selected interval
- `Daily` — complete daily series with AR/no-AR flag
- `Events` — location-specific post-processed episodes
- `Summary` — compact result summary

## Extending the project

Potential next additions include:

- other ARTMIP Tier-2 methods and reanalyses;
- batch extraction from an uploaded CSV of locations;
- selectable event definitions;
- optional ERA5 IVT enrichment;
- maps of event footprints;
- comparison between ARTMIP algorithms;
- DOI/version metadata and citation export.

## Citation

Please cite the ARTMIP/GDEX dataset and the original ARTMIP publications appropriate to the method selected. The app is a post-processing tool and should not be cited as if it were the source catalogue itself.

## Batch mode

The Streamlit app supports batch extraction from an uploaded CSV. The required columns are:

```text
latitude,longitude
```

An optional `name` column is recommended. Example:

```csv
name,latitude,longitude
Tabriz,38.08,46.29
Tokyo,35.6762,139.6503
Sydney,-33.8688,151.2093
```

The same processing settings (dataset, year range, interval, buffer, minimum pixels, event gap, and minimum event length) are applied to every location in the batch.

Batch output includes:

- `ARTMIP_batch_catalogue.xlsx` — one workbook with a `Batch_Summary` sheet and separate 6-hourly, daily, and event sheets for each location.
- `ARTMIP_batch_outputs.zip` — the batch workbook plus per-location CSV files for 6-hourly activity, daily activity, events, and metadata.

The app validates coordinate ranges before starting and continues to the next location when one location fails, recording the error in the batch summary.

For large batches, remember that extraction is computationally intensive. Annual NetCDF files are downloaded once and then reused from the local cache for subsequent locations.
