import os
import subprocess
import sqlite3

subjects_database = "subjects.db"

def retrieve_subjects(semester: int) -> list:
    '''
    retrieves subjects for the given semester from the database
    returns a list of subject names
    '''
    subjects = []
    try:
        with sqlite3.connect(subjects_database) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM subjects WHERE semester = ?", (semester,))
            rows = cursor.fetchall()
            subjects = [row[0] for row in rows]
    except sqlite3.Error as e:
        print(f"Database error: {e}")

    return subjects

def add_sub_to_list(subjects_list: list, subject_name: str) -> None:
    '''
    adds a subject to the subjects list if not already present
    '''
    if subject_name not in subjects_list:
        subjects_list.append(subject_name)
        print(f"Added: {subject_name}")
    else:
        print(f"Subject '{subject_name}' is already in the list.")


def add_sub_to_list_int(subjects_list: list, subject_ind: int) -> None:
    '''
    adds a subject to the subjects list by retrieving it from database using subject ID
    adds the subject if not already present and if it exists in the database
    '''
    try:
        with sqlite3.connect(subjects_database) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM subjects WHERE id = ?", (subject_ind,))
            row = cursor.fetchone()

            if row is None:
                print(f"Subject with ID {subject_ind} not found in database.")
                return

            subject_name = row[0]
            add_sub_to_list(subjects_list, subject_name)

    except sqlite3.Error as e:
        print(f"Database error: {e}")


def remove_sub_from_list_int(subjects_list: list, subject_index: int) -> None:
    '''
    removes the value at that index, but first converts 1-indexing to 0-indexing
    '''
    zeroIndexed = subject_index - 1
    if 0 <= zeroIndexed < len(subjects_list):
        removed = subjects_list.pop(zeroIndexed)
        print(f"Removed: {removed}")


def display_all_subjects() -> None:
    '''
    Displays all subjects from the database as options to the user.
    '''
    print('=======================')
    print('Available Subjects:')
    print('=======================\n')

    try:
        with sqlite3.connect(subjects_database) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id, name FROM subjects ORDER BY id")
            rows = cursor.fetchall()

            if not rows:
                print("No subjects found in database.")
                return

            for row in rows:
                print(f"ID: {row[0]:>2} | {row[1]}")

    except sqlite3.Error as e:
        print(f" Database error: {e}")
    print()


def display_subs_in_list(subList: list) -> int | None:
    if not subList:
        print("No subjects in the list.")
        return None

    for idx, sub in enumerate(subList):
        print(f"{idx+1}: {sub}") # because 0 is for exiting
    val = input("Enter the index (0 to exit): ")
    if val.isdigit() and 0 <= int(val) <= len(subList):
        return int(val)
    return None


def get_section_and_course() -> tuple[str, str]:
    '''
    gets the section and course from the user
    returns a tuple of (section, course)
    '''
    section = input("Enter your section (e.g., A, B, C): ").strip().upper()
    while not ("A" <= section <= "Z" or section.isdigit()):
        print("Invalid section. Defaulting to 'A'.")
        section = input("Enter your section (e.g., A, B, C): ").strip().upper()

    list_of_courses = ["CS", "SE", "DS AI", "CE", "CYS", "AI", "DS", "CY"]
    course = input("Enter your course (e.g., CS, SE, DS AI, AI, CY): ").strip().upper()
    while course not in list_of_courses:
        print("Invalid course. Please enter a valid course code.")
        course = input("Enter your course (e.g., CS, SE, DS AI, AI, CY): ").strip().upper()

    return (section, course)


#---------------------------#
#---------------------------#
#---------------------------#
#   now the main menu code  #
#---------------------------#
#---------------------------#
#---------------------------#

def main_menu() -> list:
    section, course = get_section_and_course()
    list_of_subs = []
    
    display_all_subjects()
    print("Please select the subjects you are taking.")
    print("Enter the ID of the subject to add it.")
    print("Enter 'c' to type a custom subject name.")
    print("Enter '0' when you are done.\n")

    while True:
        choice = input("Enter Subject ID (0 to finish, 'c' for custom): ").strip().lower()
        if choice == '0':
            break
        elif choice == 'c':
            custom_sub = input("Enter custom subject name exactly as it appears in the timetable: ").strip()
            if custom_sub:
                add_sub_to_list(list_of_subs, custom_sub)
        elif choice.isdigit():
            add_sub_to_list_int(list_of_subs, int(choice))
        else:
            print("Invalid input.")

    print("\nYour selected subjects:")
    for sub in list_of_subs:
        print(f"- {sub}")
    print("\n")

    # taking user choice of removing any subject first
    user_choice = input("Do you want to remove any subject? (yes or no): ").strip().lower()
    if user_choice == "yes":
        print("The subjects you have selected:")
        
        while len(list_of_subs) > 0:
            user_choice2 = display_subs_in_list(list_of_subs)
            if user_choice2 == 0:
                break
            elif user_choice2 is None:
                print("Invalid choice")
            else:
                remove_sub_from_list_int(list_of_subs, user_choice2)

    return [list_of_subs, course, section]


# Testing stuff
# no need to check this part bruh
if __name__ == "__main__":
    main_menu()
