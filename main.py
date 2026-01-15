from databaseHandler import (
    days_of_week,
    make_database,
    insert_timetable,
    read_and_clean_classroom_df,
    read_and_clean_lab_df
)

EXCEL_FILE = "Time-Table, FSC, Fall-2025.xlsx"


def main():
    # Create both databases
    make_database('uni_timetable.db', 'CLASSROOM')
    make_database('uni_timetable_lab.db', 'LAB')

    # Process each day
    for day in days_of_week:
        try:
            # Process classrooms
            clean_df = read_and_clean_classroom_df(EXCEL_FILE, day)
            insert_timetable(clean_df, day, 'uni_timetable.db', 'Room', 'CLASSROOM')
            print(f"Inserted classroom timetable for {day}")

            # Process labs
            clean_dflab = read_and_clean_lab_df(EXCEL_FILE, day)
            insert_timetable(clean_dflab, day, 'uni_timetable_lab.db', 'Lab', 'LAB')
            print(f"Inserted lab timetable for {day}")

        except Exception as e:
            print(f"Error processing {day}: {e}")

    print("\nDatabase creation complete!")
    print("- Classroom timetable: uni_timetable.db")
    print("- Lab timetable: uni_timetable_lab.db")


if __name__ == "__main__":
    main()

