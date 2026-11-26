from pathlib import Path
from typing import Optional

from config import get_active_spreadsheet_id
from rebuild_db import build_sqlite_from_google_sheet

BASE_DIR = Path(__file__).resolve().parent
COURSE_DATABASE = str(BASE_DIR / "uni_timetable.db")
LAB_DATABASE = str(BASE_DIR / "uni_timetable_lab.db")


def main(spreadsheet_id: Optional[str] = None):
    # 1. Resolve spreadsheet ID dynamically at call time and build databases
    _, resolved_sheet_id = get_active_spreadsheet_id(override_id=spreadsheet_id)
    build_sqlite_from_google_sheet(
        resolved_sheet_id,
        course_db=COURSE_DATABASE,
        lab_db=LAB_DATABASE,
    )

    print("\nDatabase creation complete!")
    print(f"- Classroom timetable: {COURSE_DATABASE}")
    print(f"- Lab timetable: {LAB_DATABASE}")


if __name__ == "__main__":
    main()
