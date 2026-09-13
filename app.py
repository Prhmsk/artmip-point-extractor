from __future__ import annotations

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
SRC_ROOT = APP_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd
import streamlit as st

from artmip_point_extractor.catalogue import (
    DATASETS,
    ExtractionConfig,
    extract_catalogue,
)

from artmip_point_extractor.export import (
    build_batch_excel_bytes,
    build_batch_zip_bytes,
    build_excel_bytes,
    dataframe_to_csv_bytes,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="ARTMIP Point Extractor",
    page_icon="🌊",
    layout="wide",
)


# ============================================================
# HEADER
# ============================================================

st.title("🌊 ARTMIP Point-Based Atmospheric River Extractor")

st.markdown(
    """
    **A research-oriented tool for extracting location-based
    Atmospheric River (AR) activity from ARTMIP catalogues.**

    The application supports both **single-location** and **batch**
    extraction and generates **selected-interval, daily, and
    location-specific AR event catalogues** in Excel and CSV formats.
    """
)


# ============================================================
# HOW IT WORKS
# ============================================================

with st.expander("📘 How it works", expanded=True):

    st.markdown(
        """
        ### Workflow

        **1. Select analysis mode**  
        Choose between **Single location** analysis or **Batch locations**
        processing.

        **2. Define location**  
        Enter latitude, longitude, and a spatial buffer around the selected
        location.

        **3. Select ARTMIP dataset**  
        Choose the available atmospheric-river catalogue and reanalysis
        dataset.

        **4. Define the analysis period**  
        Select the start and end years for the extraction.

        **5. Configure processing parameters**  
        Define the temporal interval, minimum component size, event gap,
        minimum event duration, and regional padding.

        **6. Extract AR activity**  
        The application accesses the ARTMIP catalogue and identifies
        binary AR components intersecting the selected spatial domain.

        **7. Generate catalogues**  
        The extracted activity is organized into:
        - selected-interval AR activity
        - daily AR activity
        - reconstructed location-specific AR events

        **8. Download results**  
        Results can be exported as Excel, CSV, and ZIP files.
        """
    )


# ============================================================
# SCIENTIFIC INTERPRETATION
# ============================================================

with st.expander("🔬 Scientific interpretation"):

    st.markdown(
        """
        The extracted AR events represent **location-specific episodes
        reconstructed from ARTMIP binary atmospheric-river tags after
        applying the user-defined spatial and temporal criteria**.

        These reconstructed events should **not** be interpreted as native
        ARTMIP track identifiers.

        Event-level statistics such as length, width, and axis ratio are
        calculated as **post-processing metrics** by this application.
        """
    )


# ============================================================
# SIDEBAR CONFIGURATION
# ============================================================

with st.sidebar:

    st.header("⚙️ Analysis settings")

    # --------------------------------------------------------
    # Mode
    # --------------------------------------------------------

    st.subheader("1. Analysis mode")

    mode = st.radio(
        "Extraction mode",
        ["Single location", "Batch locations"],
        help=(
            "Choose Single location to analyze one point or "
            "Batch locations to analyze multiple coordinates from a CSV file."
        ),
    )

    # --------------------------------------------------------
    # Dataset
    # --------------------------------------------------------

    st.subheader("2. ARTMIP dataset")

    dataset_key = st.selectbox(
        "Dataset",
        options=list(DATASETS),
        format_func=lambda key: DATASETS[key].label,
        help=(
            "Select the ARTMIP atmospheric-river catalogue and "
            "reanalysis dataset used for extraction."
        ),
    )

    dataset = DATASETS[dataset_key]

    # --------------------------------------------------------
    # Period
    # --------------------------------------------------------

    st.subheader("3. Analysis period")

    start_year = st.number_input(
        "Start year",
        min_value=dataset.supported_start,
        max_value=dataset.supported_end,
        value=2000,
        step=1,
        help=(
            "First year included in the extraction period."
        ),
    )

    end_year = st.number_input(
        "End year",
        min_value=dataset.supported_start,
        max_value=dataset.supported_end,
        value=min(2019, dataset.supported_end),
        step=1,
        help=(
            "Last year included in the extraction period."
        ),
    )

    # --------------------------------------------------------
    # Processing
    # --------------------------------------------------------

    st.subheader("4. Processing parameters")

    time_step_hours = st.selectbox(
        "Extraction interval",
        [1, 3, 6, 12, 24],
        index=2,
        format_func=lambda x: f"{x}-hourly",
        help=(
            "Temporal interval used to sample the source ARTMIP tags. "
            "For the Guan & Waliser ERA5 workflow, 6-hourly is the recommended setting."
        ),
    )

    min_pixels = st.number_input(
        "Minimum component pixels",
        min_value=1,
        max_value=500,
        value=8,
        step=1,
        help=(
            "Minimum number of connected AR grid cells required for a "
            "component to be retained."
        ),
    )

    max_gap_hours = st.number_input(
        "Maximum gap within event (h)",
        min_value=1,
        max_value=168,
        value=12,
        step=1,
        help=(
            "Maximum temporal gap allowed between consecutive active "
            "timesteps when reconstructing the same AR episode."
        ),
    )

    min_timesteps = st.number_input(
        "Minimum timesteps per event",
        min_value=1,
        max_value=100,
        value=2,
        step=1,
        help=(
            "Minimum number of active timesteps required for a "
            "location-specific AR episode to be retained."
        ),
    )

    spatial_padding_deg = st.number_input(
        "Regional padding (degrees)",
        min_value=1.0,
        max_value=30.0,
        value=5.0,
        step=1.0,
        help=(
            "Additional spatial area loaded around the analysis region "
            "to support identification of complete AR components. "
            "This is different from the analysis buffer."
        ),
    )

    st.divider()

    st.info(
        "Current release: Guan & Waliser Tier-2 ERA5 "
        "(hourly source tags, sampled at the selected interval)."
    )


# ============================================================
# SINGLE LOCATION MODE
# ============================================================

if mode == "Single location":

    with st.sidebar:

        st.subheader("5. Location")

        latitude = st.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=38.1922,
            step=0.01,
            format="%.4f",
            help=(
                "Latitude of the center of the location being analyzed. "
                "Positive values represent the Northern Hemisphere; "
                "negative values represent the Southern Hemisphere."
            ),
        )

        longitude = st.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            value=45.6339,
            step=0.01,
            format="%.4f",
            help=(
                "Longitude of the center of the location being analyzed. "
                "Positive values represent east longitudes; "
                "negative values represent west longitudes."
            ),
        )

        buffer_deg = st.number_input(
            "Buffer (degrees)",
            min_value=0.05,
            max_value=10.0,
            value=0.5,
            step=0.05,
            format="%.2f",
            help=(
                "Half-width of the square spatial analysis window around "
                "the selected coordinates. For example, a 0.5° buffer "
                "means ±0.5° in latitude and longitude."
            ),
        )

        st.caption(
            "Buffer defines the spatial analysis window used to identify "
            "AR components intersecting the selected location."
        )

        run = st.button(
            "🚀 Run extraction",
            type="primary",
            use_container_width=True,
        )


    # --------------------------------------------------------
    # Initial state
    # --------------------------------------------------------

    if "result" not in st.session_state and not run:

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Latitude",
            f"{latitude:.4f}°",
        )

        c2.metric(
            "Longitude",
            f"{longitude:.4f}°",
        )

        c3.metric(
            "Buffer",
            f"±{buffer_deg:.2f}°",
        )

        st.markdown("### 🧭 What does the Buffer mean?")

        st.write(
            """
            The buffer defines the spatial area around the selected
            coordinates in which ARTMIP atmospheric-river activity is
            considered relevant to the location.

            For example, with a buffer of **0.5°**, the analysis window
            extends approximately ±0.5° in latitude and longitude from
            the specified coordinates.
            """
        )

        st.info(
            "The analysis buffer and regional padding are different: "
            "the buffer defines the target analysis domain, while regional "
            "padding provides additional surrounding data for component identification."
        )

        st.markdown("### 📊 Generated products")

        p1, p2, p3 = st.columns(3)

        p1.markdown(
            """
            **Selected interval**

            AR activity at the selected temporal interval, including
            component characteristics and spatial overlap.
            """
        )

        p2.markdown(
            """
            **Daily catalogue**

            Daily AR occurrence and aggregated activity statistics.
            """
        )

        p3.markdown(
            """
            **Event catalogue**

            Location-specific AR episodes reconstructed from consecutive
            active timesteps.
            """
        )

        st.warning(
            "Event IDs are reconstructed from location-specific AR activity "
            "and are not native ARTMIP track IDs."
        )

        st.stop()


    # --------------------------------------------------------
    # Extraction
    # --------------------------------------------------------

    if run:

        config = ExtractionConfig(
            latitude=float(latitude),
            longitude=float(longitude),
            buffer_deg=float(buffer_deg),
            start_year=int(start_year),
            end_year=int(end_year),
            min_pixels=int(min_pixels),
            max_gap_hours=int(max_gap_hours),
            min_timesteps=int(min_timesteps),
            time_step_hours=int(time_step_hours),
            spatial_padding_deg=float(spatial_padding_deg),
        )

        cache_dir = Path(".artmip_cache")

        progress = st.progress(
            0,
            text="Starting extraction…",
        )

        status = st.empty()


        def update_progress(
            value: int,
            message: str,
        ) -> None:

            progress.progress(
                max(0, min(100, value)),
                text=message,
            )

            status.caption(message)


        try:

            result = extract_catalogue(
                dataset,
                config,
                cache_dir,
                progress_callback=update_progress,
            )

            st.session_state["result"] = result

            st.session_state["result_config"] = config

            st.session_state["result_dataset"] = dataset.label

        except Exception as exc:  # noqa: BLE001

            progress.empty()

            st.error(
                f"Extraction failed: {type(exc).__name__}: {exc}"
            )

            st.stop()

        progress.empty()

        status.success(
            "Extraction completed successfully."
        )


    # --------------------------------------------------------
    # Results
    # --------------------------------------------------------

    if "result" not in st.session_state:

        st.stop()


    sixhourly, daily, events, metadata = (
        st.session_state["result"]
    )


    st.header("📊 Results")


    cols = st.columns(4)

    cols[0].metric(
        "Active timesteps",
        f"{metadata['active_timesteps']:,}",
    )

    cols[1].metric(
        "Active days",
        f"{metadata['active_days']:,}",
    )

    cols[2].metric(
        "Events",
        f"{metadata['event_count']:,}",
    )

    cols[3].metric(
        "Period",
        f"{metadata['start_year']}–{metadata['end_year']}",
    )


    # --------------------------------------------------------
    # Location + metadata
    # --------------------------------------------------------

    left, right = st.columns([1.25, 1])


    with left:

        st.markdown("#### 📍 Location")

        st.map(
            pd.DataFrame(
                {
                    "lat": [metadata["latitude"]],
                    "lon": [metadata["longitude"]],
                }
            ),
            zoom=4,
        )


    with right:

        st.markdown("#### ⚙️ Extraction metadata")

        st.dataframe(
            pd.DataFrame(
                {
                    "Parameter": list(metadata),
                    "Value": list(metadata.values()),
                }
            ),
            hide_index=True,
            use_container_width=True,
        )


    # --------------------------------------------------------
    # Selected interval catalogue
    # --------------------------------------------------------

    st.markdown("### ⏱️ Selected-interval catalogue")

    st.dataframe(
        sixhourly,
        use_container_width=True,
        hide_index=True,
    )


    # --------------------------------------------------------
    # Daily catalogue
    # --------------------------------------------------------

    st.markdown("### 📅 Daily catalogue")

    st.dataframe(
        daily,
        use_container_width=True,
        hide_index=True,
    )


    # --------------------------------------------------------
    # Events
    # --------------------------------------------------------

    st.markdown("### 🌊 Reconstructed AR Events")

    st.caption(
        "These are location-specific post-processed AR episodes, "
        "not native ARTMIP track identifiers."
    )

    st.dataframe(
        events,
        use_container_width=True,
        hide_index=True,
    )


    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    st.markdown("### 💾 Download")

    excel_bytes = build_excel_bytes(
        sixhourly,
        daily,
        events,
        metadata,
    )


    d1, d2, d3 = st.columns(3)


    d1.download_button(
        "⬇️ Download Excel workbook",
        data=excel_bytes,
        file_name=(
            f"ARTMIP_"
            f"{metadata['latitude']:.4f}_"
            f"{metadata['longitude']:.4f}_"
            f"{metadata['start_year']}_"
            f"{metadata['end_year']}.xlsx"
        ),
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
        on_click="ignore",
    )


    d2.download_button(
        "⬇️ Download activity CSV",
        data=dataframe_to_csv_bytes(sixhourly),
        file_name="ARTMIP_activity.csv",
        mime="text/csv",
        use_container_width=True,
        on_click="ignore",
    )


    d3.download_button(
        "⬇️ Download events CSV",
        data=dataframe_to_csv_bytes(events),
        file_name="ARTMIP_events.csv",
        mime="text/csv",
        use_container_width=True,
        on_click="ignore",
    )


# ============================================================
# BATCH MODE
# ============================================================

else:

    st.header("📍 Batch extraction")

    st.markdown(
        """
        Batch mode allows multiple geographic locations to be processed
        using the same ARTMIP dataset, analysis period, and processing
        parameters.
        """
    )

    st.markdown(
        """
        **Required CSV columns**

        - `latitude`
        - `longitude`

        **Optional column**

        - `name`
        """
    )


    # --------------------------------------------------------
    # Example template
    # --------------------------------------------------------

    example = pd.DataFrame(
        {
            "name": [
                "Shabestar",
                "Example_Point_2",
                "Example_Point_3",
            ],
            "latitude": [
                38.1922,
                35.6762,
                -33.8688,
            ],
            "longitude": [
                45.6339,
                139.6503,
                151.2093,
            ],
        }
    )


    st.download_button(
        "📄 Download example CSV template",
        data=example.to_csv(index=False).encode("utf-8"),
        file_name="artmip_locations_template.csv",
        mime="text/csv",
        on_click="ignore",
    )


    # --------------------------------------------------------
    # Batch settings
    # --------------------------------------------------------

    batch_buffer = st.number_input(
        "Buffer for all locations (degrees)",
        min_value=0.05,
        max_value=10.0,
        value=0.5,
        step=0.05,
        format="%.2f",
        help=(
            "Spatial buffer applied to every location in the uploaded CSV."
        ),
    )

    max_locations = st.number_input(
        "Maximum locations per batch",
        min_value=1,
        max_value=500,
        value=100,
        step=1,
        help=(
            "Maximum number of locations allowed in one batch run."
        ),
    )


    uploaded = st.file_uploader(
        "Upload locations CSV",
        type=["csv"],
        help=(
            "Upload a CSV file containing latitude and longitude columns. "
            "A name column is optional."
        ),
    )


    run_batch = st.button(
        "🚀 Run batch extraction",
        type="primary",
    )


    # --------------------------------------------------------
    # Read uploaded CSV
    # --------------------------------------------------------

    if uploaded is not None:

        try:

            locations = pd.read_csv(uploaded)

        except Exception as exc:  # noqa: BLE001

            st.error(
                f"Could not read CSV: {type(exc).__name__}: {exc}"
            )

            st.stop()


        locations.columns = [
            str(c).strip().lower()
            for c in locations.columns
        ]


        required = {
            "latitude",
            "longitude",
        }


        missing = (
            required
            - set(locations.columns)
        )


        if missing:

            st.error(
                "Missing required column(s): "
                + ", ".join(
                    sorted(missing)
                )
            )

            st.stop()


        if "name" not in locations.columns:

            locations["name"] = [
                f"location_{i + 1:04d}"
                for i in range(
                    len(locations)
                )
            ]


        locations["name"] = (
            locations["name"]
            .astype(str)
            .replace(
                {
                    "nan": ""
                }
            )
        )


        numeric_lat = pd.to_numeric(
            locations["latitude"],
            errors="coerce",
        )


        numeric_lon = pd.to_numeric(
            locations["longitude"],
            errors="coerce",
        )


        invalid = (
            numeric_lat.isna()
            | numeric_lon.isna()
            | (numeric_lat < -90)
            | (numeric_lat > 90)
            | (numeric_lon < -180)
            | (numeric_lon > 180)
        )


        if invalid.any():

            st.error(
                f"The CSV contains "
                f"{int(invalid.sum())} "
                "invalid coordinate row(s)."
            )

            st.dataframe(
                locations.loc[invalid].head(20),
                hide_index=True,
                use_container_width=True,
            )

            st.stop()


        if len(locations) > int(
            max_locations
        ):

            st.error(
                f"This batch contains "
                f"{len(locations)} locations; "
                f"the configured limit is "
                f"{int(max_locations)}."
            )

            st.stop()


        locations["latitude"] = numeric_lat

        locations["longitude"] = numeric_lon


        locations = locations[
            [
                "name",
                "latitude",
                "longitude",
            ]
        ].copy()


        st.success(
            f"{len(locations):,} "
            "location(s) loaded successfully."
        )


        st.dataframe(
            locations.head(50),
            hide_index=True,
            use_container_width=True,
        )


        # ----------------------------------------------------
        # Batch extraction
        # ----------------------------------------------------

        if run_batch:

            cache_dir = Path(
                ".artmip_cache"
            )

            batch_progress = st.progress(
                0,
                text="Starting batch…",
            )

            batch_status = st.empty()


            results: list[dict] = []


            total_locations = len(
                locations
            )


            for idx, row in locations.iterrows():

                name = (
                    str(row["name"]).strip()
                    or f"location_{idx + 1:04d}"
                )

                lat = float(
                    row["latitude"]
                )

                lon = float(
                    row["longitude"]
                )


                batch_status.info(
                    f"Location "
                    f"{idx + 1}/"
                    f"{total_locations}: "
                    f"{name} "
                    f"({lat:.4f}, {lon:.4f})"
                )


                base = (
                    idx
                    / total_locations
                ) * 100


                def location_progress(
                    value: int,
                    message: str,
                    base=base,
                    idx=idx,
                    name=name,
                ) -> None:

                    overall = (
                        base
                        + (
                            value
                            / total_locations
                        )
                    )

                    batch_progress.progress(
                        int(
                            min(
                                100,
                                overall,
                            )
                        ),
                        text=(
                            f"{name}: "
                            f"{message}"
                        ),
                    )


                config = ExtractionConfig(
                    latitude=lat,
                    longitude=lon,
                    buffer_deg=float(
                        batch_buffer
                    ),
                    start_year=int(
                        start_year
                    ),
                    end_year=int(
                        end_year
                    ),
                    min_pixels=int(
                        min_pixels
                    ),
                    max_gap_hours=int(
                        max_gap_hours
                    ),
                    min_timesteps=int(
                        min_timesteps
                    ),
                    time_step_hours=int(
                        time_step_hours
                    ),
                    spatial_padding_deg=float(
                        spatial_padding_deg
                    ),
                )


                try:

                    (
                        sixhourly,
                        daily,
                        events,
                        metadata,
                    ) = extract_catalogue(
                        dataset,
                        config,
                        cache_dir,
                        progress_callback=(
                            location_progress
                        ),
                    )


                    results.append(
                        {
                            "name": name,
                            "sixhourly": sixhourly,
                            "daily": daily,
                            "events": events,
                            "metadata": metadata,
                        }
                    )


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
                                "buffer_deg": float(
                                    batch_buffer
                                ),
                                "start_year": int(
                                    start_year
                                ),
                                "end_year": int(
                                    end_year
                                ),
                                "active_timesteps": 0,
                                "active_days": 0,
                                "event_count": 0,
                                "status": "FAILED",
                                "error": (
                                    f"{type(exc).__name__}: "
                                    f"{exc}"
                                ),
                            },
                        }
                    )


                    batch_status.warning(
                        f"{name}: extraction failed; "
                        "continuing with next location."
                    )


            st.session_state[
                "batch_results"
            ] = results


            batch_progress.progress(
                100,
                text="Batch extraction completed",
            )


            batch_status.success(
                f"Finished "
                f"{total_locations:,} "
                "location(s)."
            )


    # --------------------------------------------------------
    # Batch results
    # --------------------------------------------------------

    if "batch_results" in st.session_state:

        results = st.session_state[
            "batch_results"
        ]


        ok = [
            r
            for r in results
            if r["metadata"].get(
                "status"
            ) != "FAILED"
        ]


        failed = [
            r
            for r in results
            if r["metadata"].get(
                "status"
            ) == "FAILED"
        ]


        c1, c2, c3 = st.columns(3)


        c1.metric(
            "Locations",
            len(results),
        )


        c2.metric(
            "Successful",
            len(ok),
        )


        c3.metric(
            "Failed",
            len(failed),
        )


        summary = pd.DataFrame(
            [
                {
                    "name": r["name"],
                    "latitude": r[
                        "metadata"
                    ].get("latitude"),
                    "longitude": r[
                        "metadata"
                    ].get("longitude"),
                    "active_timesteps": r[
                        "metadata"
                    ].get(
                        "active_timesteps",
                        0,
                    ),
                    "active_days": r[
                        "metadata"
                    ].get(
                        "active_days",
                        0,
                    ),
                    "event_count": r[
                        "metadata"
                    ].get(
                        "event_count",
                        0,
                    ),
                    "status": r[
                        "metadata"
                    ].get(
                        "status",
                        "OK",
                    ),
                    "error": r[
                        "metadata"
                    ].get(
                        "error",
                        "",
                    ),
                }
                for r in results
            ]
        )


        st.markdown(
            "### 📋 Batch summary"
        )


        st.dataframe(
            summary,
            hide_index=True,
            use_container_width=True,
        )


        batch_excel = (
            build_batch_excel_bytes(
                results
            )
        )


        batch_zip = (
            build_batch_zip_bytes(
                results
            )
        )


        d1, d2 = st.columns(2)


        d1.download_button(
            "⬇️ Download batch Excel",
            data=batch_excel,
            file_name=(
                "ARTMIP_batch_catalogue.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
            on_click="ignore",
        )


        d2.download_button(
            "⬇️ Download batch ZIP",
            data=batch_zip,
            file_name=(
                "ARTMIP_batch_outputs.zip"
            ),
            mime="application/zip",
            use_container_width=True,
            on_click="ignore",
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Data source: NSF NCAR GDEX ARTMIP Tier-2 Reanalysis "
    "Source Data and Catalogues "
    "(DOI 10.26024/RAWV-YX53)."
)
