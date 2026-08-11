from databaseHandler import (
    days_of_week,
    make_database,
    insert_timetable,
    read_and_clean_classroom_df,
    read_and_clean_lab_df,
    fetch_timetable_for_section,
    days_of_week,
    get_sheets_service
)

from main_menu import (
    main_menu
)

SPREADSHEET_ID = "1vlTuotLw34fedME3gNQj09cZw-todVomxAiu5P1wZ6Q"

COURSE_DATABASE = "uni_timetable.db"
LAB_DATABASE = "uni_timetable_lab.db"

def main():
    # 1. Create databases and get timetable data from google sheets
    make_database(COURSE_DATABASE, 'CLASSROOM')
    make_database(LAB_DATABASE, 'LAB')
    
    service = get_sheets_service()

    for day in days_of_week:
        try:
            # classroom setup
            clean_df = read_and_clean_classroom_df(service, SPREADSHEET_ID, day)
            insert_timetable(clean_df, day, COURSE_DATABASE, 'Room', 'CLASSROOM')
            print(f"Inserted classroom timetable for {day}")
            
            # lab setup
            clean_dflab = read_and_clean_lab_df(service, SPREADSHEET_ID, day)
            insert_timetable(clean_dflab, day, LAB_DATABASE, 'Lab', 'LAB')
            print(f"Inserted lab timetable for {day}")

        except Exception as e:
            print(f"Error processing {day}: {e}")

    print("\nDatabase creation complete!")
    print("- Classroom timetable: uni_timetable.db")
    print("- Lab timetable: uni_timetable_lab.db")





if __name__ == "__main__":
    # 1. build the database
    main()
