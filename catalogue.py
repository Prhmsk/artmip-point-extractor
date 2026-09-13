from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd
import requests
import xarray as xr
from scipy import ndimage


@dataclass(frozen=True)
class ExtractionConfig:
    latitude: float
    longitude: float
    buffer_deg: float = 0.5
    start_year: int = 2000
    end_year: int = 2019
    min_pixels: int = 8
    max_gap_hours: int = 12
    min_timesteps: int = 2
    time_step_hours: int = 6
    spatial_padding_deg: float = 5.0


@dataclass(frozen=True)
class DatasetDefinition:
    key: str
    label: str
    relative_dir: str
    filename_template: str
    source_url: str
    temporal_native: str
    supported_start: int
    supported_end: int


DATASETS: dict[str, DatasetDefinition] = {
    "guan_waliser_era5": DatasetDefinition(
        key="guan_waliser_era5",
        label="Guan & Waliser — ERA5 Tier-2",
        relative_dir="catalogues/ERA5/guan_waliser",
        filename_template=(
            "ERA5.ar_tag.GuanWaliser_v2.1hr.{year}0101-{year}1231.nc"
        ),
        source_url="https://gdex.ucar.edu/datasets/d651018/",
        temporal_native="hourly",
        supported_start=2000,
        supported_end=2019,
    )
}


EMPTY_COLUMNS = [
    "time",
    "ARTMIP_AR",
    "component_id",
    "n_pixels",
    "overlap_pixels",
    "component_fraction_in_buffer",
    "length_km",
    "width_km",
    "axis_ratio",
]


def resolve_download_urls(dataset: DatasetDefinition, year: int) -> list[str]:
    filename = dataset.filename_template.format(year=year)
    rel = dataset.relative_dir
    return [
        f"https://osdf-director.osg-htc.org/ncar/gdex/d651018/{rel}/{filename}",
        f"https://data.gdex.ucar.edu/d651018/{rel}/{filename}",
        f"https://osdf-data.gdex.ucar.edu/ncar/gdex/d651018/{rel}/{filename}",
    ]


def download_file(
    dataset: DatasetDefinition,
    year: int,
    cache_dir: Path,
    overwrite: bool = False,
    retries: int = 3,
    min_bytes: int = 1_000_000,
    status_callback: Callable[[str], None] | None = None,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = dataset.filename_template.format(year=year)
    local_file = cache_dir / filename

    if local_file.exists() and not overwrite and local_file.stat().st_size >= min_bytes:
        if status_callback:
            status_callback(f"Using cached file: {filename}")
        return local_file

    errors: list[str] = []
    for url in resolve_download_urls(dataset, year):
        for attempt in range(1, retries + 1):
            tmp_file = local_file.with_suffix(local_file.suffix + ".part")
            try:
                if status_callback:
                    status_callback(
                        f"Downloading {year}: attempt {attempt}/{retries}"
                    )
                with requests.get(
                    url,
                    stream=True,
                    timeout=(30, 600),
                    allow_redirects=True,
                    headers={"User-Agent": "ARTMIP-Point-Extractor/1.0"},
                ) as response:
                    response.raise_for_status()
                    total = 0
                    with tmp_file.open("wb") as handle:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                handle.write(chunk)
                                total += len(chunk)
                if total < min_bytes:
                    raise RuntimeError(f"Downloaded file is too small: {total} bytes")
                tmp_file.replace(local_file)
                return local_file
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url} | attempt {attempt}: {type(exc).__name__}: {exc}")
                if tmp_file.exists():
                    tmp_file.unlink(missing_ok=True)
                if attempt < retries:
                    time.sleep(2 * attempt)

    raise RuntimeError("; ".join(errors[-6:]))


def _find_coord_name(ds: xr.Dataset, candidates: Iterable[str]) -> str | None:
    for name in candidates:
        if name in ds.coords or name in ds.variables:
            return name
    return None


def _find_time_name(ds: xr.Dataset) -> str:
    name = _find_coord_name(ds, ["time", "valid_time", "datetime", "date"])
    if name is None:
        raise ValueError("Could not identify the time coordinate.")
    return name


def _find_tag_variable(ds: xr.Dataset) -> str:
    preferred = ["ar_tag", "AR_tag", "artag", "tag", "AR", "ar"]
    for name in preferred:
        if name in ds.data_vars:
            return name
    candidates = [
        name
        for name in ds.data_vars
        if "tag" in name.lower() or name.lower() == "ar" or "river" in name.lower()
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        "Could not uniquely identify the AR tag variable. "
        f"Available variables: {list(ds.data_vars)}"
    )


def standardize_dataset(ds: xr.Dataset) -> xr.Dataset:
    lat_name = _find_coord_name(ds, ["lat", "latitude"])
    lon_name = _find_coord_name(ds, ["lon", "longitude"])
    time_name = _find_time_name(ds)
    if lat_name is None or lon_name is None:
        raise ValueError("Latitude and longitude coordinates were not found.")

    rename: dict[str, str] = {}
    if lat_name != "lat":
        rename[lat_name] = "lat"
    if lon_name != "lon":
        rename[lon_name] = "lon"
    if time_name != "time":
        rename[time_name] = "time"
    return ds.rename(rename) if rename else ds


def _normalize_longitudes(ds: xr.Dataset) -> xr.Dataset:
    lon = ds["lon"]
    values = lon.values
    if np.nanmax(values) > 180:
        new_lon = ((lon + 180) % 360) - 180
        ds = ds.assign_coords(lon=new_lon).sortby("lon")
    return ds


def _select_time_grid(ds: xr.Dataset, year: int, step_hours: int) -> xr.Dataset:
    target = pd.date_range(
        start=f"{year}-01-01 00:00",
        end=f"{year}-12-31 18:00",
        freq=f"{step_hours}h",
    )
    available = pd.DatetimeIndex(pd.to_datetime(ds["time"].values))
    missing = target.difference(available)
    if len(missing) > 0:
        # Nearest is acceptable only when exact timestamps are not present.
        # Reject matches that are too far from the requested timestamp.
        selected = ds.sel(time=xr.DataArray(target, dims="time"), method="nearest")
        matched = pd.DatetimeIndex(pd.to_datetime(selected["time"].values))
        offsets = np.abs((matched.values - target.values).astype("timedelta64[s]").astype(np.int64))
        if len(offsets) and offsets.max() > step_hours * 1800:
            raise ValueError(
                "The ARTMIP file does not contain reliable timestamps for the requested interval."
            )
        return selected
    return ds.sel(time=xr.DataArray(target, dims="time"))


def load_tag_year(
    file_path: Path,
    year: int,
    config: ExtractionConfig,
) -> tuple[xr.DataArray, str]:
    # Keep the source lazy until after spatial/temporal selection.
    # This is important because ARTMIP files are global and can be large.
    opened = xr.open_dataset(file_path, decode_times=True)
    ds = standardize_dataset(opened)

    ds = _normalize_longitudes(ds)
    if ds.sizes.get("lat", 0) > 1 and float(ds.lat[0]) > float(ds.lat[-1]):
        ds = ds.sortby("lat")
    # Read only a compact regional window around the requested point.
    # A 5-degree minimum padding preserves connected AR components around the buffer
    # while avoiding the cost of loading the full global grid.
    pad = max(float(config.spatial_padding_deg), float(config.buffer_deg) + 1.0)
    lat_lo = max(-90.0, config.latitude - pad)
    lat_hi = min(90.0, config.latitude + pad)
    ds = ds.sel(lat=slice(lat_lo, lat_hi))

    lon_min = ((config.longitude - pad + 180.0) % 360.0) - 180.0
    lon_max = ((config.longitude + pad + 180.0) % 360.0) - 180.0
    if lon_min <= lon_max:
        ds = ds.sel(lon=slice(lon_min, lon_max))
    else:
        left = ds.sel(lon=slice(lon_min, 180.0))
        right = ds.sel(lon=slice(-180.0, lon_max))
        ds = xr.concat([left, right], dim="lon").sortby("lon")

    if ds.sizes.get("lat", 0) == 0 or ds.sizes.get("lon", 0) == 0:
        raise ValueError("The requested location does not intersect the ARTMIP grid.")
    if float(ds.lat[0]) > float(ds.lat[-1]):
        ds = ds.sortby("lat")

    ds = _select_time_grid(ds, year, config.time_step_hours)
    tag_name = _find_tag_variable(ds)
    tag = ds[tag_name].transpose("time", "lat", "lon").load()
    ds.close()
    return tag, tag_name


def create_location_mask(
    lat: np.ndarray,
    lon: np.ndarray,
    center_lat: float,
    center_lon: float,
    buffer_deg: float,
) -> np.ndarray:
    # Supports longitude wrap-around using the shortest angular distance.
    dlon = np.abs(((lon[None, :] - center_lon + 180.0) % 360.0) - 180.0)
    dlat = np.abs(lat[:, None] - center_lat)
    return (dlat <= buffer_deg) & (dlon <= buffer_deg)


def component_geometry(
    mask: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
) -> tuple[float, float, float]:
    yy, xx = np.where(mask)
    if len(xx) < 2:
        return np.nan, np.nan, np.nan

    lat_values = lat[yy]
    lon_values = lon[xx]
    lat0 = np.mean(lat_values)
    x = lon_values * 111.32 * np.cos(np.deg2rad(lat0))
    y = lat_values * 111.32
    xy = np.column_stack([x, y])
    xy -= xy.mean(axis=0)
    if len(xy) < 2:
        return np.nan, np.nan, np.nan

    cov = np.cov(xy, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    principal = xy @ eigvecs[:, order]
    length_km = np.ptp(principal[:, 0])
    width_km = np.ptp(principal[:, 1])
    ratio = length_km / width_km if width_km > 0 else np.nan
    return float(length_km), float(width_km), float(ratio)


def extract_year(
    tag: xr.DataArray,
    config: ExtractionConfig,
) -> pd.DataFrame:
    lat = tag["lat"].values
    lon = tag["lon"].values
    times = pd.DatetimeIndex(pd.to_datetime(tag["time"].values))
    location_mask = create_location_mask(
        lat,
        lon,
        config.latitude,
        config.longitude,
        config.buffer_deg,
    )

    tags = np.asarray(tag.values)
    structure = np.ones((3, 3), dtype=bool)
    records: list[dict] = []

    for t, timestamp in enumerate(times):
        ar_mask = np.isfinite(tags[t]) & (tags[t] == 1)
        if not ar_mask.any():
            continue

        labels, n_components = ndimage.label(ar_mask, structure=structure)
        candidates: list[dict] = []
        for component_id in range(1, n_components + 1):
            component = labels == component_id
            n_pixels = int(component.sum())
            if n_pixels < config.min_pixels:
                continue
            overlap_mask = component & location_mask
            if not overlap_mask.any():
                continue
            length_km, width_km, axis_ratio = component_geometry(component, lat, lon)
            candidates.append(
                {
                    "time": timestamp,
                    "ARTMIP_AR": 1,
                    "component_id": component_id,
                    "n_pixels": n_pixels,
                    "overlap_pixels": int(overlap_mask.sum()),
                    "component_fraction_in_buffer": int(overlap_mask.sum()) / n_pixels,
                    "length_km": length_km,
                    "width_km": width_km,
                    "axis_ratio": axis_ratio,
                }
            )

        if candidates:
            # Keep the largest spatial component when multiple AR components intersect the buffer.
            best = max(candidates, key=lambda item: (item["overlap_pixels"], item["n_pixels"]))
            records.append(best)

    return pd.DataFrame.from_records(records, columns=EMPTY_COLUMNS)


def make_daily_dataset(
    step: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    daily = pd.DataFrame({"date": dates})
    if step.empty:
        daily["ARTMIP_AR"] = 0
        daily["n_AR_timesteps"] = 0
        daily["mean_overlap_fraction"] = np.nan
        daily["max_axis_ratio"] = np.nan
        return daily

    tmp = step.copy()
    tmp["date"] = pd.to_datetime(tmp["time"]).dt.normalize()
    agg = (
        tmp.groupby("date")
        .agg(
            n_AR_timesteps=("time", "size"),
            mean_overlap_fraction=("component_fraction_in_buffer", "mean"),
            max_axis_ratio=("axis_ratio", "max"),
        )
        .reset_index()
    )
    daily = daily.merge(agg, on="date", how="left")
    daily["n_AR_timesteps"] = daily["n_AR_timesteps"].fillna(0).astype(int)
    daily["ARTMIP_AR"] = (daily["n_AR_timesteps"] > 0).astype(int)
    return daily


def build_events(
    step: pd.DataFrame,
    max_gap_hours: int = 12,
    min_timesteps: int = 2,
    time_step_hours: int = 6,
) -> pd.DataFrame:
    columns = [
        "event_id", "start", "end", "n_timesteps", "duration_h", "n_days",
        "max_length_km", "max_width_km", "max_axis_ratio", "mean_overlap_fraction",
    ]
    if step.empty:
        return pd.DataFrame(columns=columns)

    data = step.sort_values("time").drop_duplicates("time").reset_index(drop=True).copy()
    gaps = data["time"].diff().dt.total_seconds().div(3600)
    data["event_id"] = gaps.fillna(0).gt(max_gap_hours).cumsum() + 1

    rows: list[dict] = []
    for event_id, group in data.groupby("event_id"):
        n = len(group)
        if n < min_timesteps:
            continue
        start = group["time"].min()
        end = group["time"].max()
        duration_h = (end - start).total_seconds() / 3600 + time_step_hours
        rows.append(
            {
                "event_id": int(event_id),
                "start": start,
                "end": end,
                "n_timesteps": n,
                "duration_h": duration_h,
                "n_days": group["time"].dt.normalize().nunique(),
                "max_length_km": group["length_km"].max(),
                "max_width_km": group["width_km"].max(),
                "max_axis_ratio": group["axis_ratio"].max(),
                "mean_overlap_fraction": group["component_fraction_in_buffer"].mean(),
            }
        )

    events = pd.DataFrame(rows, columns=columns)
    if not events.empty:
        events = events.sort_values("start").reset_index(drop=True)
        events["event_id"] = np.arange(1, len(events) + 1)
    return events


def extract_catalogue(
    dataset: DatasetDefinition,
    config: ExtractionConfig,
    cache_dir: Path,
    progress_callback: Callable[[int, str], None] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    if config.start_year > config.end_year:
        raise ValueError("Start year must be less than or equal to end year.")
    if not (-90 <= config.latitude <= 90):
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not (-180 <= config.longitude <= 180):
        raise ValueError("Longitude must be between -180 and 180 degrees.")
    if config.buffer_deg <= 0:
        raise ValueError("Buffer must be greater than zero.")

    all_steps: list[pd.DataFrame] = []
    years = list(range(config.start_year, config.end_year + 1))
    for i, year in enumerate(years, start=1):
        if year < dataset.supported_start or year > dataset.supported_end:
            raise ValueError(
                f"{dataset.label} supports {dataset.supported_start}-{dataset.supported_end}; got {year}."
            )
        if progress_callback:
            progress_callback(int((i - 1) / len(years) * 100), f"Preparing {year}")
        file_path = download_file(
            dataset,
            year,
            cache_dir,
            status_callback=lambda message: progress_callback(int((i - 1) / len(years) * 100), message)
            if progress_callback else None,
        )
        tag, tag_name = load_tag_year(file_path, year, config)
        step_year = extract_year(tag, config)
        if not step_year.empty:
            all_steps.append(step_year)
        if progress_callback:
            progress_callback(int(i / len(years) * 90), f"Processed {year} ({len(step_year)} active timesteps)")

    if all_steps:
        step = pd.concat(all_steps, ignore_index=True).sort_values("time").drop_duplicates("time")
        step = step.reset_index(drop=True)
    else:
        step = pd.DataFrame(columns=EMPTY_COLUMNS)

    daily = make_daily_dataset(
        step,
        start_date=f"{config.start_year}-01-01",
        end_date=f"{config.end_year}-12-31",
    )
    events = build_events(step, config.max_gap_hours, config.min_timesteps, config.time_step_hours)

    metadata = {
        "dataset": dataset.label,
        "dataset_key": dataset.key,
        "latitude": config.latitude,
        "longitude": config.longitude,
        "buffer_deg": config.buffer_deg,
        "start_year": config.start_year,
        "end_year": config.end_year,
        "min_pixels": config.min_pixels,
        "max_gap_hours": config.max_gap_hours,
        "min_timesteps": config.min_timesteps,
        "time_step_hours": config.time_step_hours,
        "spatial_padding_deg": config.spatial_padding_deg,
        "native_temporal_resolution": dataset.temporal_native,
        "source_url": dataset.source_url,
        "description": (
            "Events are post-processed episodes formed after restricting binary AR tags "
            "to components intersecting the user-defined buffer; they are not native ARTMIP track IDs."
        ),
        "active_timesteps": int(step["ARTMIP_AR"].sum()) if not step.empty else 0,
        "active_days": int(daily["ARTMIP_AR"].sum()),
        "event_count": int(len(events)),
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "tag_variable": tag_name,
    }
    if progress_callback:
        progress_callback(100, "Extraction complete")
    return step, daily, events, metadata
