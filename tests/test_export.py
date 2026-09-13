import pandas as pd

from artmip_point_extractor.export import build_batch_excel_bytes, build_batch_zip_bytes


def _item(name):
    return {
        "name": name,
        "sixhourly": pd.DataFrame({"time": pd.to_datetime(["2000-01-01"]), "ARTMIP_AR": [1]}),
        "daily": pd.DataFrame({"date": pd.to_datetime(["2000-01-01"]), "ARTMIP_AR": [1]}),
        "events": pd.DataFrame({"event_id": [1], "duration_h": [6]}),
        "metadata": {
            "dataset": "Guan & Waliser — ERA5 Tier-2",
            "latitude": 1.0,
            "longitude": 2.0,
            "buffer_deg": 0.5,
            "start_year": 2000,
            "end_year": 2000,
            "active_timesteps": 1,
            "active_days": 1,
            "event_count": 1,
        },
    }


def test_batch_excel_smoke():
    raw = build_batch_excel_bytes([_item("Shabestar"), _item("Tokyo")])
    assert raw[:2] == b"PK"
    assert len(raw) > 2000


def test_batch_zip_smoke():
    raw = build_batch_zip_bytes([_item("Shabestar")])
    assert raw[:2] == b"PK"
    assert b"batch_summary.xlsx" in raw
