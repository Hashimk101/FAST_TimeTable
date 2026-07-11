"""
sheets_to_df.py

Converts raw Google Sheets API data (list of lists) into the same clean
DataFrames your old xlsx-based code produced:

  read_and_clean_classroom_df()  ->  Room | 08:30-09:50 | 10:00-11:20 | ...
  read_and_clean_lab_df()        ->  Lab  | 08:30-11:15 | 11:30-02:15 | ...

Drop-in replacement: the rest of your database_handler.py works unchanged.
"""

import pandas as pd
from pandas import DataFrame

# ── helpers ──────────────────────────────────────────────────────────────────

CLASSROOM_TIME_SLOTS = [
    "08:30-09:50",
    "10:00-11:20",
    "11:30-12:50",
    "01:00-02:20",
    "02:30-03:50",
    "03:55-05:15",
    "05:20-06:40",
    "06:45-08:05",
]

LAB_TIME_SLOTS = [
    "08:30-11:15",
    "11:30-02:15",
    "02:30-05:15",
    "05:20-08:05",
]

# Classroom rows end before the lab separator row (which starts with "Lab")
# Lab rows start after that separator


def _raw_to_dataframe(raw: list[list]) -> DataFrame:
    """Turn raw API values (list of lists, ragged) into a uniform DataFrame."""
    if not raw:
        return DataFrame()
    max_cols = max(len(r) for r in raw)
    padded = [r + [""] * (max_cols - len(r)) for r in raw]
    return DataFrame(padded)


def _find_header_row(df: DataFrame, first_col_value: str) -> int:
    """Return the row index whose first non-empty cell equals first_col_value."""
    for i, row in df.iterrows():
        vals = [str(v).strip() for v in row if str(v).strip()]
        if vals and vals[0] == first_col_value:
            return i
    raise ValueError(f"Header row with '{first_col_value}' not found")


def _find_timeslot_columns(header_row: pd.Series, slots: list[str]) -> dict:
    """
    Map each canonical time-slot string to the column index in the raw sheet.
    Matches on startswith so minor whitespace/suffix differences don't break it.
    Returns {slot_string: col_index}.
    """
    mapping = {}
    for slot in slots:
        for col_idx, val in enumerate(header_row):
            cell = str(val).strip()
            if cell.startswith(slot[:5]):   # match on first 5 chars (e.g. "08:30")
                mapping[slot] = col_idx
                break
    return mapping


def _extract_section(df: DataFrame, header_row_idx: int,
                     location_col_idx: int, slot_mapping: dict,
                     location_col_name: str, separator: str) -> DataFrame:
    """
    Generic extractor for both classroom and lab sections.
    Skips rows where the location cell is empty or equals the separator keyword.
    """
    records = []
    for i in range(header_row_idx + 1, len(df)):
        row = df.iloc[i]
        location = str(row.iloc[location_col_idx]).strip()

        # Stop at next major section separator
        if location.lower() == separator.lower():
            break
        if not location or location == "nan":
            continue

        entry = {location_col_name: location}
        for slot, col_idx in slot_mapping.items():
            val = str(row.iloc[col_idx]).strip() if col_idx < len(row) else ""
            entry[slot] = val if val and val != "nan" else "NIL"

        records.append(entry)

    result = DataFrame(records)
    if result.empty:
        return result
    result = result.fillna("NIL")
    return result


# ── public API ────────────────────────────────────────────────────────────────

def sheets_to_classroom_df(raw_values: list[list]) -> DataFrame:
    """
    Convert raw Google Sheets API values for one day-sheet into a clean
    classroom DataFrame identical to read_and_clean_classroom_df().

    Columns: Room | 08:30-09:50 | 10:00-11:20 | ... | 06:45-08:05
    """
    df = _raw_to_dataframe(raw_values)

    room_header_idx = _find_header_row(df, "Room")
    header_row = df.iloc[room_header_idx]

    slot_mapping = _find_timeslot_columns(header_row, CLASSROOM_TIME_SLOTS)

    return _extract_section(
        df,
        header_row_idx=room_header_idx,
        location_col_idx=0,
        slot_mapping=slot_mapping,
        location_col_name="Room",
        separator="Lab",          # stops when it hits the Lab section
    )


def sheets_to_lab_df(raw_values: list[list]) -> DataFrame:
    """
    Convert raw Google Sheets API values for one day-sheet into a clean
    lab DataFrame identical to read_and_clean_lab_df().

    Columns: Lab | 08:30-11:15 | 11:30-02:15 | 02:30-05:15 | 05:20-08:05
    """
    df = _raw_to_dataframe(raw_values)

    lab_header_idx = _find_header_row(df, "Lab")
    header_row = df.iloc[lab_header_idx]

    slot_mapping = _find_timeslot_columns(header_row, LAB_TIME_SLOTS)

    return _extract_section(
        df,
        header_row_idx=lab_header_idx,
        location_col_idx=0,
        slot_mapping=slot_mapping,
        location_col_name="Lab",
        separator="STOP_NEVER",   # lab section goes to end of sheet
    )


# ── verification: test against the xlsx you already have ─────────────────────

if __name__ == "__main__":
    import sys

    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "Time-Table__FSC__Fall-2025.xlsx"
    day = sys.argv[2] if len(sys.argv) > 2 else "Monday"

    print(f"Loading {xlsx_path}, sheet={day}")

    # Simulate what the Google Sheets API returns: raw list of lists
    raw_df = pd.read_excel(xlsx_path, sheet_name=day, header=None, dtype=str)
    raw_values = raw_df.fillna("").values.tolist()

    classroom = sheets_to_classroom_df(raw_values)
    lab       = sheets_to_lab_df(raw_values)

    print(f"\n=== Classroom ({len(classroom)} rows) ===")
    print("Columns:", list(classroom.columns))
    print(classroom.head(10).to_string())

    print(f"\n=== Lab ({len(lab)} rows) ===")
    print("Columns:", list(lab.columns))
    print(lab.head(10).to_string())
