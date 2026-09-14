from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd


# ============================================================
# CSV EXPORT
# ============================================================

def dataframe_to_csv_bytes(
    df: pd.DataFrame
) -> bytes:

    return (
        df.to_csv(index=False)
        .encode("utf-8")
    )


# ============================================================
# WRITE SHEET
# ============================================================

def _write_df_sheet(
    writer: pd.ExcelWriter,
    df: pd.DataFrame,
    sheet_name: str
) -> None:

    sheet_name = sheet_name[:31]

    df.to_excel(
        writer,
        sheet_name=sheet_name,
        index=False
    )


# ============================================================
# FORMAT WORKBOOK
# ============================================================

def _format_workbook(
    writer: pd.ExcelWriter,
    sheets: dict[str, pd.DataFrame]
) -> None:

    workbook = writer.book

    header = workbook.add_format(
        {
            "bold": True,
            "font_color": "white",
            "bg_color": "#176B87",
        }
    )

    date_fmt = workbook.add_format(
        {
            "num_format": "yyyy-mm-dd hh:mm"
        }
    )

    day_fmt = workbook.add_format(
        {
            "num_format": "yyyy-mm-dd"
        }
    )


    for sheet_name, df in sheets.items():

        sheet_name = sheet_name[:31]

        if sheet_name not in writer.sheets:
            continue

        ws = writer.sheets[sheet_name]


        ws.freeze_panes(
            1,
            0
        )


        if len(df.columns) > 0:

            ws.autofilter(
                0,
                0,
                max(len(df), 1),
                len(df.columns)-1
            )


        for col_idx, col in enumerate(df.columns):

            ws.write(
                0,
                col_idx,
                col,
                header
            )


            width = min(
                max(
                    len(str(col))+2,
                    12
                ),
                36
            )


            if len(df) > 0:

                try:

                    sample = (
                        df[col]
                        .astype("string")
                        .fillna("")
                        .head(300)
                    )

                    max_len = int(
                        sample
                        .str.len()
                        .max()
                    )

                    width = min(
                        max(
                            width,
                            max_len+2
                        ),
                        36
                    )

                except Exception:

                    pass


            ws.set_column(
                col_idx,
                col_idx,
                width
            )


        if "time" in df.columns:

            idx = df.columns.get_loc(
                "time"
            )

            ws.set_column(
                idx,
                idx,
                20,
                date_fmt
            )


        if "date" in df.columns:

            idx = df.columns.get_loc(
                "date"
            )

            ws.set_column(
                idx,
                idx,
                14,
                day_fmt
            )


        for field in [
            "start",
            "end"
        ]:

            if field in df.columns:

                idx = df.columns.get_loc(
                    field
                )

                ws.set_column(
                    idx,
                    idx,
                    20,
                    date_fmt
                )


# ============================================================
# SINGLE LOCATION EXCEL
# ============================================================

def build_excel_bytes(
    sixhourly: pd.DataFrame,
    daily: pd.DataFrame,
    events: pd.DataFrame,
    metadata: dict,
) -> bytes:


    output = BytesIO()


    sheets = {

        "Metadata":
            pd.DataFrame(
                {
                    "Parameter":
                        list(metadata.keys()),

                    "Value":
                        list(metadata.values())
                }
            ),


        "6-hourly":
            sixhourly,


        "Daily":
            daily,


        "Events":
            events,


        "Summary":

            pd.DataFrame(
                [
                    [
                        "Dataset",
                        metadata.get("dataset")
                    ],
                    [
                        "Latitude",
                        metadata.get("latitude")
                    ],
                    [
                        "Longitude",
                        metadata.get("longitude")
                    ],
                    [
                        "Buffer",
                        metadata.get("buffer_deg")
                    ],
                    [
                        "Start year",
                        metadata.get("start_year")
                    ],
                    [
                        "End year",
                        metadata.get("end_year")
                    ],
                    [
                        "Active timesteps",
                        metadata.get("active_timesteps")
                    ],
                    [
                        "Active days",
                        metadata.get("active_days")
                    ],
                    [
                        "Events",
                        metadata.get("event_count")
                    ],
                ],
                columns=[
                    "Metric",
                    "Value"
                ]
            )
    }


    with pd.ExcelWriter(
        output,
        engine="xlsxwriter"
    ) as writer:


        for name, df in sheets.items():

            _write_df_sheet(
                writer,
                df,
                name
            )


        _format_workbook(
            writer,
            sheets
        )


    return output.getvalue()



# ============================================================
# BATCH EXCEL
# ============================================================

def build_batch_excel_bytes(
    results: list[dict]
) -> bytes:


    output = BytesIO()

    summary_rows = []

    all_sheets = {}


    with pd.ExcelWriter(
        output,
        engine="xlsxwriter"
    ) as writer:


        for item in results:

            name = str(
                item["name"]
            )


            safe = (
                "".join(
                    c if c.isalnum()
                    else "_"
                    for c in name
                )
                .strip("_")
                or
                "location"
            )


            prefix = safe[:18]


            meta = item["metadata"]


            summary_rows.append(
                {
                    "name": name,
                    "latitude": meta.get("latitude"),
                    "longitude": meta.get("longitude"),
                    "active_timesteps": meta.get("active_timesteps",0),
                    "active_days": meta.get("active_days",0),
                    "event_count": meta.get("event_count",0),
                }
            )


            sheets = {

                f"{prefix}_6h":
                    item["sixhourly"],

                f"{prefix}_daily":
                    item["daily"],

                f"{prefix}_events":
                    item["events"],

            }


            for sheet, df in sheets.items():

                sheet = sheet[:31]

                _write_df_sheet(
                    writer,
                    df,
                    sheet
                )

                all_sheets[sheet] = df



        summary_df = pd.DataFrame(
            summary_rows
        )


        _write_df_sheet(
            writer,
            summary_df,
            "Batch_Summary"
        )


        all_sheets["Batch_Summary"] = summary_df


        _format_workbook(
            writer,
            all_sheets
        )


    return output.getvalue()



# ============================================================
# BATCH ZIP
# ============================================================

def build_batch_zip_bytes(
    results: list[dict]
) -> bytes:


    output = BytesIO()


    with ZipFile(
        output,
        "w",
        compression=ZIP_DEFLATED
    ) as archive:


        archive.writestr(
            "batch_summary.xlsx",
            build_batch_excel_bytes(results)
        )


        for item in results:

            name = str(item["name"])


            safe = (
                "".join(
                    c if c.isalnum()
                    else "_"
                    for c in name
                )
                .strip("_")
                or
                "location"
            )


            archive.writestr(
                f"{safe}_6hourly.csv",
                dataframe_to_csv_bytes(
                    item["sixhourly"]
                )
            )


            archive.writestr(
                f"{safe}_daily.csv",
                dataframe_to_csv_bytes(
                    item["daily"]
                )
            )


            archive.writestr(
                f"{safe}_events.csv",
                dataframe_to_csv_bytes(
                    item["events"]
                )
            )


    return output.getvalue()
