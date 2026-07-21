import sqlite3
import pandas as pd
from databaseHandler import get_sheets_service, get_raw_sheet
from sheets_to_df import _find_header_row, _find_timeslot_columns, CLASSROOM_TIME_SLOTS, _raw_to_dataframe

SPREADSHEET_ID = "1ZQJqdArlwCS965uw4sbJrB6j8rEPfZerMT7X8qkXSzY"

def check():
    service = get_sheets_service()
    raw = get_raw_sheet(service, SPREADSHEET_ID, "Tuesday")
    df = _raw_to_dataframe(raw)
    
    room_header_idx = _find_header_row(df, "Room")
    header_row = df.iloc[room_header_idx]
    
    slot_mapping = _find_timeslot_columns(header_row, CLASSROOM_TIME_SLOTS)
    
    # Sort slot mapping by column index
    sorted_slots = sorted(slot_mapping.items(), key=lambda x: x[1])
    
    for i, row in df.iterrows():
        if row[0] == 'D-506':
            print("D-506 Row data (Block parsing):")
            
            for j in range(len(sorted_slots)):
                slot, start_col = sorted_slots[j]
                
                # The end column is the start of the next slot, or the end of the row
                end_col = sorted_slots[j+1][1] if j+1 < len(sorted_slots) else len(row)
                
                # Get all non-empty values in this block
                block_vals = []
                for c in range(start_col, end_col):
                    val = str(row.iloc[c]).strip() if c < len(row) else ""
                    if val and val != 'nan':
                        block_vals.append(val)
                
                final_val = " | ".join(block_vals) if block_vals else "NIL"
                print(f"  {slot} (Cols {start_col}-{end_col-1}): {final_val}")

if __name__ == '__main__':
    check()
