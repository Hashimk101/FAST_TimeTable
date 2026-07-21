"""
Rebuild the SQLite databases from the Google Sheets API.
This is just the DB rebuild portion of main.py, without the interactive menu.
"""
from databaseHandler import (
    days_of_week,
    make_database,
    insert_timetable,
    read_and_clean_classroom_df,
    read_and_clean_lab_df,
    get_sheets_service
)

SPREADSHEET_ID = "1ZQJqdArlwCS965uw4sbJrB6j8rEPfZerMT7X8qkXSzY"
COURSE_DATABASE = "uni_timetable.db"
LAB_DATABASE = "uni_timetable_lab.db"

def rebuild():
    make_database(COURSE_DATABASE, 'CLASSROOM')
    make_database(LAB_DATABASE, 'LAB')

    service = get_sheets_service()

    for day in days_of_week:
        try:
            clean_df = read_and_clean_classroom_df(service, SPREADSHEET_ID, day)
            insert_timetable(clean_df, day, COURSE_DATABASE, 'Room', 'CLASSROOM')
            print(f"Inserted classroom timetable for {day}")

            clean_dflab = read_and_clean_lab_df(service, SPREADSHEET_ID, day)
            insert_timetable(clean_dflab, day, LAB_DATABASE, 'Lab', 'LAB')
            print(f"Inserted lab timetable for {day}")

        except Exception as e:
            print(f"Error processing {day}: {e}")
            import traceback
            traceback.print_exc()

    print("\nDatabase rebuild complete!")

if __name__ == "__main__":
    rebuild()
