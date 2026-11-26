"""
Rebuild the SQLite databases from the Google Sheets API.
This is just the DB rebuild portion of main.py, without the interactive menu.
"""

import argparse
from pathlib import Path
import sqlite3
from typing import Optional

from config import get_active_spreadsheet_id
from databaseHandler import (
    correct_typos_in_db,
    days_of_week,
    get_day_sheet_mapping,
    get_sheets_service,
    insert_timetable,
    make_database,
    read_and_clean_classroom_df,
    read_and_clean_lab_df,
)

BASE_DIR = Path(__file__).resolve().parent
COURSE_DATABASE = str(BASE_DIR / "uni_timetable.db")
LAB_DATABASE = str(BASE_DIR / "uni_timetable_lab.db")


def build_sqlite_from_google_sheet(
    spreadsheet_id: str,
    course_db: str = COURSE_DATABASE,
    lab_db: str = LAB_DATABASE,
) -> dict:
    """
    Fetches all visible day sheets from Google Sheets API and populates `course_db`
    and `lab_db`. Fails loudly on missing day sheets or per-day parsing errors.
    """
    make_database(course_db, "CLASSROOM")
    make_database(lab_db, "LAB")

    service = get_sheets_service()
    sheet_mapping = get_day_sheet_mapping(service, spreadsheet_id, refresh=True)
    print(f"Discovered day sheet mapping (hidden sheets skipped): {sheet_mapping}")

    available_days = [d for d in days_of_week if d in sheet_mapping]
    if not available_days:
        raise RuntimeError(
            f"SHEET_STRUCTURE_INVALID: No visible day sheets found in spreadsheet '{spreadsheet_id}'."
        )

    for day in days_of_week:
        if day not in sheet_mapping:
            print(f"Skipping {day}: No visible/active sheet found.")
            continue

        actual_sheet = sheet_mapping[day]
        try:
            clean_df = read_and_clean_classroom_df(service, spreadsheet_id, actual_sheet)
            insert_timetable(clean_df, day, course_db, "Room", "CLASSROOM")
            print(f"Inserted classroom timetable for {day} (from sheet '{actual_sheet}')")

            clean_dflab = read_and_clean_lab_df(service, spreadsheet_id, actual_sheet)
            insert_timetable(clean_dflab, day, lab_db, "Lab", "LAB")
            print(f"Inserted lab timetable for {day} (from sheet '{actual_sheet}')")
        except Exception as exc:
            print(f"Error processing {day} (sheet '{actual_sheet}'): {exc}")
            raise

    print("\nApplying fuzzy matching to correct typos...")
    correct_typos_in_db(course_db)
    correct_typos_in_db(lab_db)

    with sqlite3.connect(course_db) as conn_t:
        theory_count = conn_t.execute("SELECT COUNT(*) FROM timetable").fetchone()[0]
    with sqlite3.connect(lab_db) as conn_l:
        lab_count = conn_l.execute("SELECT COUNT(*) FROM timetable").fetchone()[0]

    if theory_count + lab_count == 0:
        raise RuntimeError(
            f"SHEET_STRUCTURE_INVALID: Parsed 0 timetable slots from spreadsheet '{spreadsheet_id}'."
        )

    return {
        "spreadsheet_id": spreadsheet_id,
        "theory_slots": int(theory_count),
        "lab_slots": int(lab_count),
    }


def rebuild(
    spreadsheet_id: Optional[str] = None,
    skip_static_gen: bool = True,
    course_db: str = COURSE_DATABASE,
    lab_db: str = LAB_DATABASE,
):
    semester_id, resolved_sheet_id = get_active_spreadsheet_id(override_id=spreadsheet_id)
    print(f"Rebuilding SQLite databases for semester={semester_id or 'local'} sheet={resolved_sheet_id}...")
    summary = build_sqlite_from_google_sheet(
        resolved_sheet_id,
        course_db=course_db,
        lab_db=lab_db,
    )

    if not skip_static_gen:
        from generate_static_json import generate_static_data

        print("\nRegenerating static frontend data files...")
        generate_static_data()

    print("\nDatabase rebuild complete!")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild SQLite timetable databases from Google Sheets.")
    parser.add_argument("--spreadsheet-id", type=str, default=None, help="Optional explicit Google Sheet ID override")
    parser.add_argument(
        "--skip-static-gen",
        action="store_true",
        default=True,
        help="Skip calling generate_static_data() (default behavior)",
    )
    args = parser.parse_args()
    rebuild(spreadsheet_id=args.spreadsheet_id, skip_static_gen=args.skip_static_gen)
