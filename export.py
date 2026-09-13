from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _write_df_sheet(writer: pd.ExcelWriter, df: pd.DataFrame, sheet_name: str) -> None:
    # Excel sheet names have a 31-character limit.
    sheet_name = sheet_name[:31]
    df.to_excel(writer, sheet_name=sheet_name, index=False)


def _format_workbook(writer: pd.ExcelWriter, sheets: dict[str, pd.DataFrame]) -> None:
    workbook = writer.book
    header = workbook.add_format({"bold": True, "font_color": "white", "bg_color": "#176B87", "border": 0})
    date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})
    day_fmt = workbook.add_format({"num_format": "yyyy-mm-dd"})

    for sheet_name, df in sheets.items():
        ws = writer.sheets[sheet_name[:31]]
        ws.freeze_panes(1, 0)
        if len(df.columns):
            ws.autofilter(0, 0, max(len(df), 1), len(df.columns) - 1)
        for col_idx, col in enumerate(df.columns):
            ws.write(0, col_idx, col, header)
            width = min(max(len(str(col)) + 2, 12), 36)
            if len(df) > 0:
                sample = df[col].astype(str).head(300)
                max_len = int(sample.map(len).max()) if not sample.empty else 0
                width = min(max(width, max_len + 2), 36)
            ws.set_column(col_idx, col_idx, width)

        if "time" in df.columns:
            idx = df.columns.get_loc("time")
            ws.set_column(idx, idx, 20, date_fmt)
        if "date" in df.columns:
            idx = df.columns.get_loc("date")
            ws.set_column(idx, idx, 14, day_fmt)
        for field in ("start", "end"):
            if field in df.columns:
                idx = df.columns.get_loc(field)
                ws.set_column(idx, idx, 20, date_fmt)


def build_excel_bytes(
    sixhourly: pd.DataFrame,
    daily: pd.DataFrame,
    events: pd.DataFrame,
    metadata: dict,
) -> bytes:
    output = BytesIO()
    sheets: dict[str, pd.DataFrame] = {
        "Metadata": pd.DataFrame({"Parameter": list(metadata.keys()), "Value": list(metadata.values())}),
        "6-hourly": sixhourly,
        "Daily": daily,
        "Events": events,
        "Summary": pd.DataFrame(
            [
                ["Dataset", metadata.get("dataset")],
                ["Latitude", metadata.get("latitude")],
                ["Longitude", metadata.get("longitude")],
                ["Buffer (deg)", metadata.get("buffer_deg")],
                ["Start year", metadata.get("start_year")],
                ["End year", metadata.get("end_year")],
                ["Active timesteps", metadata.get("active_timesteps")],
                ["Active days", metadata.get("active_days")],
                ["Events", metadata.get("event_count")],
            ],
            columns=["Metric", "Value"],
        ),
    }
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for name, df in sheets.items():
            _write_df_sheet(writer, df, name)
        _format_workbook(writer, sheets)
    return output.getvalue()


def build_batch_excel_bytes(results: list[dict]) -> bytes:
    """Create one workbook containing a batch summary and per-location sheets."""
    output = BytesIO()
    summary_rows: list[dict] = []

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for item in results:
            name = str(item["name"])
            safe = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "location"
            prefix = safe[:18]
            sixhourly = item["sixhourly"]
            daily = item["daily"]
            events = item["events"]
            meta = item["metadata"]

            summary_rows.append(
                {
                    "name": name,
                    "latitude": meta["latitude"],
                    "longitude": meta["longitude"],
                    "active_timesteps": meta["active_timesteps"],
                    "active_days": meta["active_days"],
                    "event_count": meta["event_count"],
                    "start_year": meta["start_year"],
                    "end_year": meta["end_year"],
                }
            )

            sheets = {
                f"{prefix}_6h": sixhourly,
                f"{prefix}_daily": daily,
                f"{prefix}_events": events,
            }
            for sheet_name, df in sheets.items():
                # Ensure unique sheet names in case two names normalize identically.
                base = sheet_name[:31]
                candidate = base
                i = 2
                while candidate in writer.sheets:
                    suffix = f"_{i}"
                    candidate = base[:31 - len(suffix)] + suffix
                    i += 1
                _write_df_sheet(writer, df, candidate)

        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_excel(writer, sheet_name="Batch_Summary", index=False)
        _format_workbook(writer, {"Batch_Summary": summary_df})

    return output.getvalue()


def build_batch_zip_bytes(results: list[dict]) -> bytes:
    """Create a ZIP with one Excel workbook and CSV files per location."""
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("batch_summary.xlsx", build_batch_excel_bytes(results))
        for item in results:
            name = str(item["name"])
            safe = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "location"
            archive.writestr(f"{safe}_6hourly.csv", dataframe_to_csv_bytes(item["sixhourly"]))
            archive.writestr(f"{safe}_daily.csv", dataframe_to_csv_bytes(item["daily"]))
            archive.writestr(f"{safe}_events.csv", dataframe_to_csv_bytes(item["events"]))
            archive.writestr(
                f"{safe}_metadata.csv",
                dataframe_to_csv_bytes(
                    pd.DataFrame({"Parameter": list(item["metadata"].keys()), "Value": list(item["metadata"].values())})
                ),
            )
    return output.getvalue()
