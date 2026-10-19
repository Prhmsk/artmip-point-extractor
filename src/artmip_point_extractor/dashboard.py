"""Research-oriented single-location results UI for ARTMIP Point Extractor.

Install as src/artmip_point_extractor/dashboard.py.
This module does not modify native ARTMIP tags or reconstruction logic.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st


def _annual_activity(daily: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Annual observation-day coverage and derived event-start counts."""
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"])
    d["year"] = d["date"].dt.year
    d["ARTMIP_AR"] = pd.to_numeric(d["ARTMIP_AR"], errors="coerce")
    annual = d.groupby("year", as_index=False).agg(
        calendar_days=("date", "nunique"),
        assessed_days=("ARTMIP_AR", "count"),
        active_days=("ARTMIP_AR", "sum"),
    )
    annual["active_day_pct"] = (
        100 * annual["active_days"] / annual["assessed_days"].replace(0, float("nan"))
    )
    if not events.empty and "start" in events:
        starts = pd.to_datetime(events["start"], errors="coerce").dropna()
        counts = starts.dt.year.value_counts()
        annual["derived_event_starts"] = annual["year"].map(counts).fillna(0).astype(int)
    else:
        annual["derived_event_starts"] = 0
    return annual


def _monthly_activity(daily: pd.DataFrame) -> pd.DataFrame:
    """Calendar-month frequency based on daily flags, not only positive detections."""
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"])
    d["ARTMIP_AR"] = pd.to_numeric(d["ARTMIP_AR"], errors="coerce")
    d["month"] = d["date"].dt.month
    grouped = d.groupby("month").agg(
        assessed_days=("ARTMIP_AR", "count"),
        active_days=("ARTMIP_AR", "sum"),
    ).reindex(range(1, 13), fill_value=0)
    grouped["active_day_pct"] = 100 * grouped["active_days"] / grouped["assessed_days"].replace(0, float("nan"))
    grouped.index = pd.Index(
        [pd.Timestamp(2001, m, 1).strftime("%b") for m in grouped.index], name="month"
    )
    return grouped


def render_single_dashboard(
    steps: pd.DataFrame,
    daily: pd.DataFrame,
    events: pd.DataFrame,
    metadata: dict,
) -> None:
    """Render scientific results while preserving the caller's download workflow."""
    st.subheader("Extraction results")
    a, b, c, d = st.columns(4)
    a.metric("Active sampled steps", f"{int(metadata.get('active_timesteps', len(steps))):,}",
             help="AR-positive records at the selected sampling interval; not all possible time steps.")
    b.metric("AR-active days", f"{int(metadata.get('active_days', 0)):,}")
    c.metric("Derived AR episodes", f"{int(metadata.get('event_count', len(events))):,}",
             help="Post-processed local episodes; not native ARTMIP tracking IDs.")
    d.metric("Analysis period", f"{metadata.get('start_year', '?')}–{metadata.get('end_year', '?')}")

    st.info("**Scientific interpretation:** AR occurrence originates from ARTMIP binary tags. "
            "Connected components, their geometry, and local episodes are post-processing outputs. "
            "A local episode ID is not an ARTMIP track ID.")

    overview, annual_tab, season_tab, event_tab, data_tab, metadata_tab = st.tabs([
        "Overview", "Annual variability", "Seasonality", "Derived events",
        "Data explorer", "Metadata & methods",
    ])
    annual = _annual_activity(daily, events)
    monthly = _monthly_activity(daily)

    with overview:
        left, right = st.columns([1, 1])
        with left:
            st.markdown("**Target location**")
            lat, lon = metadata.get("latitude"), metadata.get("longitude")
            if lat is not None and lon is not None:
                st.map(pd.DataFrame({"lat": [float(lat)], "lon": [float(lon)]}), zoom=4)
            st.caption(f"Spatial buffer: ±{metadata.get('buffer_deg', '?')}° in the configured location mask. "
                       "Degrees are not a fixed physical distance.")
        with right:
            st.markdown("**Annual AR-active days**")
            if not annual.empty:
                st.bar_chart(annual.set_index("year")[["active_days"]], y_label="Days", x_label="Year")
            else:
                st.info("No daily records to display.")
        st.markdown("**Interpretation**")
        st.write("Activity counts refer to the chosen location and sampling interval. "
                 "Reported episodes depend on the specified minimum pixels, event gap, "
                 "and minimum timestep settings.")

    with annual_tab:
        st.markdown("**Annual frequency of AR-active days**")
        if annual.empty:
            st.info("No data available.")
        else:
            st.line_chart(annual.set_index("year")[["active_day_pct"]],
                          y_label="Active days / assessed days (%)", x_label="Year")
            st.markdown("**Number of locally reconstructed episodes by start year**")
            st.bar_chart(annual.set_index("year")[["derived_event_starts"]],
                         y_label="Episodes", x_label="Start year")
            st.dataframe(annual, hide_index=True, use_container_width=True)
        st.caption("Descriptive annual summaries only; no statistically significant trend is inferred.")

    with season_tab:
        st.markdown("**Calendar-month AR-active-day frequency**")
        st.bar_chart(monthly[["active_day_pct"]], y_label="Active days / assessed days (%)", x_label="Month")
        st.dataframe(monthly.reset_index(), hide_index=True, use_container_width=True)
        st.caption("Each month pools all days in the selected years. Frequency uses the "
                   "daily calendar denominator rather than AR-positive steps alone. "
                   "The present extractor does not explicitly distinguish missing source observations from non-AR days.")

    with event_tab:
        if events.empty:
            st.info("No reconstructed events pass the current processing criteria.")
        else:
            view = events.copy()
            view["start"] = pd.to_datetime(view["start"], errors="coerce")
            view["end"] = pd.to_datetime(view["end"], errors="coerce")
            if "duration_h" in view:
                duration = pd.to_numeric(view["duration_h"], errors="coerce")
                valid = duration.dropna()
                if not valid.empty:
                    min_h, max_h = float(valid.min()), float(valid.max())
                    if min_h < max_h:
                        low, high = st.slider("Episode duration (hours)", min_h, max_h,
                                              (min_h, max_h))
                        view = view[duration.between(low, high)]
                    else:
                        st.caption(f"All episodes have duration {min_h:g} h.")
            st.dataframe(view, hide_index=True, use_container_width=True)
            st.caption("Lengths, widths, axis ratios, and event durations are derived estimates; "
                       "they are not native ARTMIP track geometry or duration variables.")

    with data_tab:
        selected = st.radio("Catalogue", ["Selected-interval AR-positive steps", "Daily calendar", "Derived events"],
                            horizontal=True)
        source = {
            "Selected-interval AR-positive steps": steps,
            "Daily calendar": daily,
            "Derived events": events,
        }[selected]
        st.caption(f"{len(source):,} records · {len(source.columns):,} columns")
        st.dataframe(source, use_container_width=True, hide_index=True)
        if selected == "Selected-interval AR-positive steps":
            st.caption("Only positive detected steps are stored here; absence of a row "
                       "does not explicitly encode observation completeness.")

    with metadata_tab:
        st.dataframe(pd.DataFrame({"Parameter": list(metadata), "Value": list(metadata.values())}),
                     hide_index=True, use_container_width=True)
        st.markdown("**Definitions and limitations**")
        st.write("The input is a binary AR identification catalogue. The extraction "
                 "algorithm identifies connected components meeting selection criteria "
                 "and creates location-specific episodes from gaps between positive samples. "
                 "Derived episode starts, durations, and geometry depend on user-defined settings.")
        st.write("Annual and monthly displays are descriptive. Missing-data completeness, "
                 "trend significance, and catalogue-to-catalogue uncertainty are not assessed here.")
