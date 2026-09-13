import numpy as np
import pandas as pd
import xarray as xr

from artmip_point_extractor.export import build_excel_bytes
from artmip_point_extractor.catalogue import (
    ExtractionConfig,
    build_events,
    component_geometry,
    create_location_mask,
    extract_year,
)


def make_test_tag():
    lat = np.array([0.0, 1.0, 2.0, 3.0])
    lon = np.array([10.0, 11.0, 12.0, 13.0])
    time = pd.date_range("2000-01-01", periods=4, freq="6h")
    values = np.zeros((4, 4, 4), dtype=np.int8)
    values[:, 1:3, 1:3] = 1
    return xr.DataArray(values, coords={"time": time, "lat": lat, "lon": lon}, dims=("time", "lat", "lon"))


def test_location_mask():
    mask = create_location_mask(
        np.array([0.0, 1.0, 2.0]),
        np.array([10.0, 11.0, 12.0]),
        1.0,
        11.0,
        0.01,
    )
    assert mask.sum() == 1
    assert mask[1, 1]


def test_component_geometry():
    mask = np.zeros((3, 4), dtype=bool)
    mask[1, 1:3] = True
    length, width, ratio = component_geometry(mask, np.array([0.0, 1.0, 2.0]), np.array([10.0, 11.0, 12.0, 13.0]))
    assert length > 0
    assert width == 0
    assert np.isnan(ratio)


def test_extract_year_and_events():
    tag = make_test_tag()
    config = ExtractionConfig(
        latitude=1.5,
        longitude=11.5,
        buffer_deg=0.6,
        min_pixels=2,
        time_step_hours=6,
        min_timesteps=2,
    )
    step = extract_year(tag, config)
    assert len(step) == 4
    assert step["ARTMIP_AR"].eq(1).all()

    events = build_events(step, max_gap_hours=12, min_timesteps=2, time_step_hours=6)
    assert len(events) == 1
    assert events.loc[0, "n_timesteps"] == 4
    assert events.loc[0, "duration_h"] == 24


def test_excel_export_smoke():
    metadata = {
        "dataset": "Guan & Waliser — ERA5 Tier-2",
        "latitude": 38.1922,
        "longitude": 45.6339,
        "buffer_deg": 0.5,
        "start_year": 2000,
        "end_year": 2019,
        "active_timesteps": 0,
        "active_days": 0,
        "event_count": 0,
    }
    raw = build_excel_bytes(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), metadata)
    assert raw[:2] == b"PK"
    assert len(raw) > 1000
