import os
import subprocess
import sqlite3

subjects_database = "subjects.db"
total_semesters = 8

def select_semester() -> int:
    '''
    returns the semester number selected by the user as an integer(1-8 inclusive)
    '''
    while True:
        input_semester = input(f"Enter semester number (1-{total_semesters}): ")
        if input_semester.isdigit():
            semester_number = int(input_semester)
            if 1 <= semester_number <= total_semesters:
                return semester_number

        # clear screen code
        subprocess.run('cls' if os.name == 'nt' else 'clear', shell=True)
        print("Invalid input. Please try again.")


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

def remove_sub_from_list(subjects_list: list, subject_name: str) -> None:
    '''
    removes a subject from the subjects list if present
    '''
    if subject_name in subjects_list:
        subjects_list.remove(subject_name)

def display_all_subjects(semester: int) -> int|None:
    '''
    Displays all subjects from the database as options to the user.
    Returns the selected subject ID as an integer.
    Note: It will provide the names up to that semester only.
    '''
    print('=======================')
    print('Choose by ID:')
    print('=======================\n')

    try:
        with sqlite3.connect(subjects_database) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id, name, semester FROM subjects WHERE semester <= ? ORDER BY semester",
                (semester,)
            )
            rows = cursor.fetchall()

            if not rows:
                print(f"No subjects found for semesters 1-{semester}.")
                return None

            # Display all subjects
            for row in rows:
                print(f"ID: {row[0]}, Name: {row[1]}, Semester: {row[2]}")

    except sqlite3.Error as e:
        print(f" Database error: {e}")
        return None

    print()
    input_id = input("Enter Subject ID: ")
    if input_id.isdigit():
        return int(input_id)
    else:
        print("Invalid input.")
        return None



#---------------------------#
#---------------------------#
#---------------------------#
#   now the main menu code  #
#---------------------------#
#---------------------------#
#---------------------------#


# def main_menu() -> None:
#     semester = select_semester()
#     print("These are the subjects that are offered in this semester: \n")
#     list_of_subs = retrieve_subjects(semester)
#     for sub in list_of_subs:
#         print(sub)
#     user_choice = input("Do you want to add any remove any subject???(yes or no): ")
#     if user_choice.lower().strip() == "yes":
#         print("the list of subjects you want to enter are here:")
#         print("Press 0 for exiting")
#         user_choice2 = display_all_subjects(semester)
#         while user_choice2 != 0:
#             if user_choice2 == None:
#                 print("Invalid choice")
#                 print("Press 0 for exiting")
#             else:


# Testing stuff
# no need to check this part bruh
if __name__ == "__main__":
    num = display_all_subjects(1)
    print(f"Selected Subject ID: {num}")
