from __future__ import annotations

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
SRC_ROOT = APP_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import io
import zipfile

import pandas as pd
import streamlit as st

from artmip_point_extractor.catalogue import DATASETS, ExtractionConfig, extract_catalogue
from artmip_point_extractor.export import (
    build_batch_excel_bytes,
    build_batch_zip_bytes,
    build_excel_bytes,
    dataframe_to_csv_bytes,
)

st.set_page_config(page_title="ARTMIP Point Extractor", page_icon="🌊", layout="wide")

st.title("ARTMIP Point-Based Data Extractor")
st.caption("Extract atmospheric-river activity from ARTMIP binary tag catalogues for one or many locations.")

# ------------------------- Sidebar configuration -------------------------
with st.sidebar:
    st.header("Mode")
    mode = st.radio("Extraction mode", ["Single location", "Batch locations"])

    st.header("ARTMIP dataset")
    dataset_key = st.selectbox("Dataset", options=list(DATASETS), format_func=lambda key: DATASETS[key].label)
    dataset = DATASETS[dataset_key]

    st.header("Period")
    start_year = st.number_input("Start year", min_value=dataset.supported_start, max_value=dataset.supported_end, value=2000, step=1)
    end_year = st.number_input("End year", min_value=dataset.supported_start, max_value=dataset.supported_end, value=min(2019, dataset.supported_end), step=1)

    st.header("Processing")
    time_step_hours = st.selectbox("Extraction interval", [1, 3, 6, 12, 24], index=2)
    min_pixels = st.number_input("Minimum component pixels", min_value=1, max_value=500, value=8, step=1)
    max_gap_hours = st.number_input("Maximum gap within event (h)", min_value=1, max_value=168, value=12, step=1)
    min_timesteps = st.number_input("Minimum timesteps per event", min_value=1, max_value=100, value=2, step=1)
    spatial_padding_deg = st.number_input("Regional padding (degrees)", min_value=1.0, max_value=30.0, value=5.0, step=1.0)

    st.divider()
    st.info("Current release: Guan & Waliser Tier-2 ERA5 (hourly source tags, sampled at the selected interval).")

# ------------------------- Single mode -------------------------
if mode == "Single location":
    with st.sidebar:
        st.header("Location")
        latitude = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=38.1922, step=0.01, format="%.4f")
        longitude = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=45.6339, step=0.01, format="%.4f")
        buffer_deg = st.number_input("Buffer (degrees)", min_value=0.05, max_value=10.0, value=0.5, step=0.05, format="%.2f")
        run = st.button("Run extraction", type="primary", use_container_width=True)

    if "result" not in st.session_state and not run:
        c1, c2, c3 = st.columns(3)
        c1.metric("Default latitude", f"{latitude:.4f}°")
        c2.metric("Default longitude", f"{longitude:.4f}°")
        c3.metric("Default buffer", f"±{buffer_deg:.2f}°")
        st.markdown("### How it works")
        st.write("The app downloads annual ARTMIP NetCDF files, applies a regional subset, identifies AR components intersecting the requested buffer, and creates time-step, daily and post-processed event catalogues.")
        st.warning("Event IDs are reconstructed from location-specific activity and are not native ARTMIP track IDs.")
        st.stop()

    if run:
        config = ExtractionConfig(
            latitude=float(latitude), longitude=float(longitude), buffer_deg=float(buffer_deg),
            start_year=int(start_year), end_year=int(end_year), min_pixels=int(min_pixels),
            max_gap_hours=int(max_gap_hours), min_timesteps=int(min_timesteps),
            time_step_hours=int(time_step_hours), spatial_padding_deg=float(spatial_padding_deg),
        )
        cache_dir = Path(".artmip_cache")
        progress = st.progress(0, text="Starting extraction…")
        status = st.empty()

        def update_progress(value: int, message: str) -> None:
            progress.progress(max(0, min(100, value)), text=message)
            status.caption(message)

        try:
            result = extract_catalogue(dataset, config, cache_dir, progress_callback=update_progress)
            st.session_state["result"] = result
            st.session_state["result_config"] = config
            st.session_state["result_dataset"] = dataset.label
        except Exception as exc:  # noqa: BLE001
            progress.empty()
            st.error(f"Extraction failed: {type(exc).__name__}: {exc}")
            st.stop()
        progress.empty()
        status.success("Extraction completed successfully.")

    if "result" not in st.session_state:
        st.stop()

    sixhourly, daily, events, metadata = st.session_state["result"]
    st.subheader("Results")
    cols = st.columns(4)
    cols[0].metric("Active timesteps", f"{metadata['active_timesteps']:,}")
    cols[1].metric("Active days", f"{metadata['active_days']:,}")
    cols[2].metric("Events", f"{metadata['event_count']:,}")
    cols[3].metric("Period", f"{metadata['start_year']}–{metadata['end_year']}")

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown("#### Location")
        st.map(pd.DataFrame({"lat": [metadata["latitude"]], "lon": [metadata["longitude"]]}), zoom=4)
    with right:
        st.markdown("#### Extraction metadata")
        st.dataframe(pd.DataFrame({"Parameter": list(metadata), "Value": list(metadata.values())}), hide_index=True, use_container_width=True)

    st.markdown("#### Selected-interval catalogue")
    st.dataframe(sixhourly, use_container_width=True, hide_index=True)
    st.markdown("#### Daily catalogue")
    st.dataframe(daily, use_container_width=True, hide_index=True)
    st.markdown("#### Events")
    st.dataframe(events, use_container_width=True, hide_index=True)

    excel_bytes = build_excel_bytes(sixhourly, daily, events, metadata)
    st.subheader("Download")
    d1, d2, d3 = st.columns(3)
    d1.download_button("Download Excel workbook", data=excel_bytes, file_name=f"ARTMIP_{metadata['latitude']:.4f}_{metadata['longitude']:.4f}_{metadata['start_year']}_{metadata['end_year']}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, on_click="ignore")
    d2.download_button("Download activity CSV", data=dataframe_to_csv_bytes(sixhourly), file_name="ARTMIP_activity.csv", mime="text/csv", use_container_width=True, on_click="ignore")
    d3.download_button("Download events CSV", data=dataframe_to_csv_bytes(events), file_name="ARTMIP_events.csv", mime="text/csv", use_container_width=True, on_click="ignore")

# ------------------------- Batch mode -------------------------
else:
    st.subheader("Batch extraction")
    st.write("Upload a CSV containing locations. Required columns: `latitude`, `longitude`. Optional column: `name`.")

    example = pd.DataFrame(
        {
            "name": ["Shabestar", "Example_Point_2"],
            "latitude": [38.1922, 35.6762],
            "longitude": [45.6339, 139.6503],
        }
    )
    st.download_button(
        "Download example CSV template",
        data=example.to_csv(index=False).encode("utf-8"),
        file_name="artmip_locations_template.csv",
        mime="text/csv",
        on_click="ignore",
    )

    uploaded = st.file_uploader("Upload locations CSV", type=["csv"])
    batch_buffer = st.number_input("Buffer for all locations (degrees)", min_value=0.05, max_value=10.0, value=0.5, step=0.05, format="%.2f")
    max_locations = st.number_input("Maximum locations per batch", min_value=1, max_value=500, value=100, step=1)
    run_batch = st.button("Run batch extraction", type="primary", use_container_width=False)

    if uploaded is not None:
        try:
            locations = pd.read_csv(uploaded)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not read CSV: {type(exc).__name__}: {exc}")
            st.stop()

        locations.columns = [str(c).strip().lower() for c in locations.columns]
        required = {"latitude", "longitude"}
        missing = required - set(locations.columns)
        if missing:
            st.error(f"Missing required column(s): {', '.join(sorted(missing))}")
            st.stop()

        if "name" not in locations.columns:
            locations["name"] = [f"location_{i+1:04d}" for i in range(len(locations))]
        locations["name"] = locations["name"].astype(str).replace({"nan": ""})

        numeric_lat = pd.to_numeric(locations["latitude"], errors="coerce")
        numeric_lon = pd.to_numeric(locations["longitude"], errors="coerce")
        invalid = numeric_lat.isna() | numeric_lon.isna() | (numeric_lat < -90) | (numeric_lat > 90) | (numeric_lon < -180) | (numeric_lon > 180)
        if invalid.any():
            st.error(f"The CSV contains {int(invalid.sum())} invalid coordinate row(s).")
            st.dataframe(locations.loc[invalid].head(20), hide_index=True, use_container_width=True)
            st.stop()
        if len(locations) > int(max_locations):
            st.error(f"This batch contains {len(locations)} locations; the configured limit is {int(max_locations)}.")
            st.stop()

        locations["latitude"] = numeric_lat
        locations["longitude"] = numeric_lon
        locations = locations[["name", "latitude", "longitude"]].copy()
        st.markdown(f"**{len(locations):,} location(s) loaded**")
        st.dataframe(locations.head(50), hide_index=True, use_container_width=True)

        if run_batch:
            cache_dir = Path(".artmip_cache")
            batch_progress = st.progress(0, text="Starting batch…")
            batch_status = st.empty()
            results: list[dict] = []

            total_locations = len(locations)
            for idx, row in locations.iterrows():
                name = str(row["name"]).strip() or f"location_{idx+1:04d}"
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                base = (idx / total_locations) * 100
                batch_status.info(f"Location {idx + 1}/{total_locations}: {name} ({lat:.4f}, {lon:.4f})")

                def location_progress(value: int, message: str, base=base, idx=idx, name=name) -> None:
                    overall = base + (value / total_locations)
                    batch_progress.progress(int(min(100, overall)), text=f"{name}: {message}")

                config = ExtractionConfig(
                    latitude=lat, longitude=lon, buffer_deg=float(batch_buffer),
                    start_year=int(start_year), end_year=int(end_year), min_pixels=int(min_pixels),
                    max_gap_hours=int(max_gap_hours), min_timesteps=int(min_timesteps),
                    time_step_hours=int(time_step_hours), spatial_padding_deg=float(spatial_padding_deg),
                )
                try:
                    sixhourly, daily, events, metadata = extract_catalogue(dataset, config, cache_dir, progress_callback=location_progress)
                    results.append({"name": name, "sixhourly": sixhourly, "daily": daily, "events": events, "metadata": metadata})
                except Exception as exc:  # noqa: BLE001
                    results.append(
                        {
                            "name": name,
                            "sixhourly": pd.DataFrame(),
                            "daily": pd.DataFrame(),
                            "events": pd.DataFrame(),
                            "metadata": {
                                "dataset": dataset.label,
                                "latitude": lat,
                                "longitude": lon,
                                "buffer_deg": float(batch_buffer),
                                "start_year": int(start_year),
                                "end_year": int(end_year),
                                "active_timesteps": 0,
                                "active_days": 0,
                                "event_count": 0,
                                "status": "FAILED",
                                "error": f"{type(exc).__name__}: {exc}",
                            },
                        }
                    )
                    batch_status.warning(f"{name}: extraction failed; continuing with next location.")

            st.session_state["batch_results"] = results
            batch_progress.progress(100, text="Batch extraction completed")
            batch_status.success(f"Finished {total_locations:,} location(s).")

    if "batch_results" in st.session_state:
        results = st.session_state["batch_results"]
        ok = [r for r in results if r["metadata"].get("status") != "FAILED"]
        failed = [r for r in results if r["metadata"].get("status") == "FAILED"]

        c1, c2, c3 = st.columns(3)
        c1.metric("Locations", len(results))
        c2.metric("Successful", len(ok))
        c3.metric("Failed", len(failed))

        summary = pd.DataFrame(
            [
                {
                    "name": r["name"],
                    "latitude": r["metadata"].get("latitude"),
                    "longitude": r["metadata"].get("longitude"),
                    "active_timesteps": r["metadata"].get("active_timesteps", 0),
                    "active_days": r["metadata"].get("active_days", 0),
                    "event_count": r["metadata"].get("event_count", 0),
                    "status": r["metadata"].get("status", "OK"),
                    "error": r["metadata"].get("error", ""),
                }
                for r in results
            ]
        )
        st.markdown("#### Batch summary")
        st.dataframe(summary, hide_index=True, use_container_width=True)

        batch_excel = build_batch_excel_bytes(results)
        batch_zip = build_batch_zip_bytes(results)
        d1, d2 = st.columns(2)
        d1.download_button("Download batch Excel", data=batch_excel, file_name="ARTMIP_batch_catalogue.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, on_click="ignore")
        d2.download_button("Download batch ZIP", data=batch_zip, file_name="ARTMIP_batch_outputs.zip", mime="application/zip", use_container_width=True, on_click="ignore")

st.divider()
st.caption("Data source: NSF NCAR GDEX ARTMIP Tier-2 Reanalysis Source Data and Catalogues (DOI 10.26024/RAWV-YX53).")
