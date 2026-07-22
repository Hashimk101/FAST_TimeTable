"""
sheets_to_df.py

Converts raw Google Sheets API grid data into clean
DataFrames. Extracts background color to determine batch names and appends them to subjects.

  read_and_clean_classroom_df()  ->  Room | 08:30-09:50 | 10:00-11:20 | ...
  read_and_clean_lab_df()        ->  Lab  | 08:30-11:15 | 11:30-02:15 | ...
"""

import pandas as pd
from pandas import DataFrame
import re

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

def _normalize_color(color_dict: dict) -> tuple:
    if not color_dict:
        return (255, 255, 255)
    r = int(round(color_dict.get('red', 0.0) * 255))
    g = int(round(color_dict.get('green', 0.0) * 255))
    b = int(round(color_dict.get('blue', 0.0) * 255))
    return (r, g, b)

def _is_color_similar(c1: tuple, c2: tuple, tolerance: int = 15) -> bool:
    return abs(c1[0] - c2[0]) <= tolerance and abs(c1[1] - c2[1]) <= tolerance and abs(c1[2] - c2[2]) <= tolerance

def _parse_batch_name(raw_name: str) -> str:
    raw_name = raw_name.strip()
    year_match = re.search(r'\(?20(\d{2})\)?', raw_name)
    if raw_name.startswith('BS'):
        if year_match:
            return f"BS {year_match.group(1)}"
        return "BS"
    elif raw_name.startswith('MS'):
        if year_match:
            return f"MS {year_match.group(1)}"
        return "MS"
    return raw_name

def _extract_legend(row_data: list) -> dict:
    legend_color_map = {}
    for row_idx in range(min(4, len(row_data))):
        cells = row_data[row_idx].get('values', [])
        for cell in cells:
            val = str(cell.get('formattedValue', '')).strip()
            if not val or val in ["Room", "Lab"] or "TimeTable" in val or "FSC" in val:
                continue
            if re.match(r'^\d{2}:\d{2}', val):
                continue
            
            fmt = cell.get('effectiveFormat', {})
            bg = fmt.get('backgroundColor', {})
            rgb = _normalize_color(bg)
            
            if _is_color_similar(rgb, (255, 255, 255), 5):
                continue
                
            clean_val = _parse_batch_name(val)
            legend_color_map[rgb] = clean_val
    return legend_color_map

def _grid_to_dataframe(row_data: list) -> DataFrame:
    if not row_data:
        return DataFrame()
        
    legend_color_map = _extract_legend(row_data)
    
    table = []
    for row in row_data:
        row_vals = []
        cells = row.get('values', [])
        for cell in cells:
            val = str(cell.get('formattedValue', '')).strip()
            if val and val != "None":
                fmt = cell.get('effectiveFormat', {})
                bg = fmt.get('backgroundColor', {})
                rgb = _normalize_color(bg)
                
                batch = None
                for l_rgb, b_name in legend_color_map.items():
                    if _is_color_similar(rgb, l_rgb, 5):
                        batch = b_name
                        break
                        
                if batch:
                    val = f"{val} [{batch}]"
            else:
                val = ""
            row_vals.append(val)
        table.append(row_vals)
        
    max_cols = max((len(r) for r in table), default=0)
    padded = [r + [""] * (max_cols - len(r)) for r in table]
    return DataFrame(padded)


def _find_header_row(df: DataFrame, first_col_value: str) -> int:
    for i, row in df.iterrows():
        # Remove batch tags for searching headers
        vals = [re.sub(r'\s*\[.*?\]', '', str(v)).strip() for v in row if str(v).strip()]
        if vals and vals[0] == first_col_value:
            return i
    raise ValueError(f"Header row with '{first_col_value}' not found")


def _find_timeslot_columns(header_row: pd.Series, slots: list[str]) -> dict:
    mapping = {}
    for slot in slots:
        for col_idx, val in enumerate(header_row):
            # Remove batch tags for matching slots
            cell = re.sub(r'\s*\[.*?\]', '', str(val)).strip()
            if cell.startswith(slot[:5]):
                mapping[slot] = col_idx
                break
    return mapping


def _extract_section(df: DataFrame, header_row_idx: int,
                     location_col_idx: int, slot_mapping: dict,
                     location_col_name: str, separator: str) -> DataFrame:
    records = []
    
    sorted_slots = sorted(slot_mapping.items(), key=lambda x: x[1])

    for i in range(header_row_idx + 1, len(df)):
        row = df.iloc[i]
        location_raw = str(row.iloc[location_col_idx])
        # Location might have a batch tag, strip it out just in case
        location = re.sub(r'\s*\[.*?\]', '', location_raw).strip()

        if location.lower() == separator.lower():
            break
        if not location or location == "nan":
            continue

        entry = {location_col_name: location}
        
        for j in range(len(sorted_slots)):
            slot, start_col = sorted_slots[j]
            end_col = sorted_slots[j+1][1] if j+1 < len(sorted_slots) else len(row)
            
            block_vals = []
            for c in range(start_col, end_col):
                val = str(row.iloc[c]).strip() if c < len(row) else ""
                if val and val != "nan":
                    block_vals.append(val)
            
            final_val = " | ".join(block_vals) if block_vals else "NIL"
            entry[slot] = final_val

        records.append(entry)

    result = DataFrame(records)
    if result.empty:
        return result
    result = result.fillna("NIL")
    return result


# ── public API ────────────────────────────────────────────────────────────────

def sheets_to_classroom_df(row_data: list) -> DataFrame:
    """
    Convert raw Google Sheets API grid data (rowData) for one day-sheet into a clean
    classroom DataFrame with batch names appended.
    """
    df = _grid_to_dataframe(row_data)

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


def sheets_to_lab_df(row_data: list) -> DataFrame:
    """
    Convert raw Google Sheets API grid data (rowData) for one day-sheet into a clean
    lab DataFrame with batch names appended.
    """
    df = _grid_to_dataframe(row_data)

    lab_header_idx = _find_header_row(df, "Lab")
    header_row = df.iloc[lab_header_idx]

    slot_mapping = _find_timeslot_columns(header_row, LAB_TIME_SLOTS)

    return _extract_section(
        df,
        header_row_idx=lab_header_idx,
        location_col_idx=0,
        slot_mapping=slot_mapping,
        location_col_name="Lab",
        separator="END",          # just a dummy separator, usually stops at EOF
    )
