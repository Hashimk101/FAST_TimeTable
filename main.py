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

SPREADSHEET_ID = "1ZQJqdArlwCS965uw4sbJrB6j8rEPfZerMT7X8qkXSzY"

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
    # 1. build the database (Optional: comment this out if DB is already built to save time)
    main()

    # 2. Get user input
    list_of_reqs = main_menu()
    if not list_of_reqs:
        print("No valid input received from main menu.")
        exit(1)

    # The values are assigned as follows:
    list_of_subs = list_of_reqs[0]
    course = list_of_reqs[1]
    section = list_of_reqs[2]
    CoSec = f"{course}-{section}"

    # 3. Fetch data
    print(f"\nGenerating timetable for {CoSec}...\n")

    # NOTE: currently this only fetches from COURSE_DATABASE (Classrooms).
    # If you need Labs, you must also query LAB_DATABASE.
    timetable = fetch_timetable_for_section(COURSE_DATABASE, CoSec, list_of_subs)

    if not timetable:
        print(f"No timetable found for {CoSec}.")
        exit(1)

    # 4. Print the Timetable
    print("=" * 60)
    print(f"{'TIMETABLE':^60}")
    print(f"{CoSec:^60}")
    print("=" * 60)

    # Iterate through days (0=Monday, 4=Friday)
    for i, day_schedule in enumerate(timetable):
        # Use days_of_week list for the label (e.g., "MONDAY")
        day_name = days_of_week[i].upper() if i < len(days_of_week) else f"DAY {i+1}"

        print(f"\n{day_name}")
        print("-" * 20)

        if not day_schedule:
            print("  [No Classes]")
            continue

        for cls in day_schedule:
            # Assuming subjectEntry has attributes: starttime, endtime, subject, location
            # Using specific formatting for alignment
            print(f"  {cls.starttime:<10} - {cls.endtime:<10} | {cls.subject:<30} | {cls.location}")

    print("\n" + "=" * 60)
