import sqlite3
import pandas as pd
from pandas import DataFrame, Series
import numpy as np

# list of working days
days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


'''
    steps to use the database handler:
    1. call make_database() once to create the database and the timetable table
'''

# database work and stuff
def make_database(db_name: str = 'uni_timetable.db', location_column: str = 'CLASSROOM'):
    '''
    Docstring for making the database and the timetable table
    it only creates the table if it does not already exist but doesnt populate it
    '''
    conn = sqlite3.connect(db_name)
    crsr = conn.cursor()

    crsr.execute(f'''CREATE TABLE IF NOT EXISTS timetable (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                DAY TEXT NOT NULL,
                START_TIME TEXT NOT NULL,
                END_TIME TEXT NOT NULL,
                SUBJECT TEXT NOT NULL,
                {location_column} TEXT NOT NULL,
                SECTION TEXT NOT NULL,

                UNIQUE(DAY, {location_column}, START_TIME) -- to avoid overlapping classes in the same classroom just in case the timetable is incorrect
                )
                ''')

    crsr.execute(''' CREATE INDEX IF NOT EXISTS idx_day_section ON timetable (DAY, SECTION) ''')
    conn.commit()
    conn.close()

def get_list_of_dicts_from_df(clean_df: DataFrame, location_col: str = 'Room') -> list:
    '''
    Docstring for get_list_of_dicts_from_df

    :param clean_df: DataFrame containing the timetable data
    :type clean_df: DataFrame
    :param location_col: Column name for room/lab (e.g., 'Room' or 'Lab')
    :type location_col: str

    :returns: list of dictionaries representing the timetable entries
    :rtype: list
    '''
    timetable_list = []

    for idx, row in clean_df.iterrows():
        location = row[location_col]

        # Loop through the time columns (skipping the first column)
        for time_slot in clean_df.columns[1:]:
            subject = row[time_slot]

            if subject == "NIL":
                continue

            entry = {
                'location': location,
                'time_slot': time_slot,
                'subject': subject,
            }

            timetable_list.append(entry)

    return timetable_list

def check_if_time_in_subject(subject: str) -> bool:
    '''
        in the uni's xlsx file, some slots have timeslot included in the subject name itself(shitty design)
        this function checks if the timeslot is included in the subject string
    '''
    if not ')' in subject:
        return False
    first, second = subject.split(')', 1)
    return bool(second.strip())

def separate_subject_and_section(subject_with_section: str) -> tuple:
    try:
        parts = subject_with_section.split('(', 1)
        subject = parts[0].strip()
        section = parts[1].replace(')', '').strip()
        return subject, section
    except IndexError:
        # This runs for "NIL" or any cell without a '('
        return subject_with_section, ""

def separate_time_and_section_from_subject(subject: str) -> tuple:
    '''
    param: subject: str -> which will be in the format "subject (section) timeslot"
    returns three values:
    1. subject name
    2. section
    3. time_slot
    '''
    subject, second = subject.split('(', 1)
    section, time_slot = second.split(')', 1)
    return subject.strip(), section.strip(), time_slot.strip()


def separate_time_slot(time_slot: str) -> tuple:
    start_time, end_time = time_slot.split('-')
    return start_time.strip(), end_time.strip()

def insert_timetable(clean_df: DataFrame, day: str, db_name: str = 'uni_timetable.db',
                     location_col: str = 'Room', db_location_col: str = 'CLASSROOM') -> None:
    '''
    Docstring for insert_timetable

    :param clean_df: DataFrame containing the timetable data to be inserted into the database
    :type clean_df: DataFrame
    :param day: The day of the week for which the timetable is being inserted
    :type day: str
    :param db_name: Database file name
    :type db_name: str
    :param location_col: DataFrame column name ('Room' or 'Lab')
    :type location_col: str
    :param db_location_col: Database column name ('CLASSROOM' or 'LAB')
    :type db_location_col: str

    returns: None
    '''
    conn = sqlite3.connect(db_name)
    crsr = conn.cursor()

    # Convert DataFrame to list of dictionaries
    timetable_list = get_list_of_dicts_from_df(clean_df, location_col)

    for entry in timetable_list:
        if check_if_time_in_subject(entry['subject']):
            subject, section, time_slot = separate_time_and_section_from_subject(entry['subject'])
            entry['subject'] = subject
            entry['section'] = section
            entry['time_slot'] = time_slot
        else:
            subject, section = separate_subject_and_section(entry['subject'])
            entry['subject'] = subject
            entry['section'] = section

        start_time, end_time = separate_time_slot(entry['time_slot'])
        entry['start_time'] = start_time
        entry['end_time'] = end_time
        del entry['time_slot']  # Remove the original time_slot key

        crsr.execute(f'''
            INSERT OR IGNORE INTO timetable (DAY, START_TIME, END_TIME, SUBJECT, {db_location_col}, SECTION)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (day, entry['start_time'], entry['end_time'], entry['subject'], entry['location'], entry['section']))
    conn.commit()
    conn.close()


def read_and_clean_classroom_df(excel_file: str, sheet_name: str) -> DataFrame:
    """Read and clean classroom timetable from Excel."""
    df = pd.read_excel(excel_file, sheet_name=sheet_name, header=4, nrows=57)
    clean_df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    clean_df = clean_df.dropna(subset=['Room'])
    clean_df = clean_df.fillna("NIL")
    return clean_df


def read_and_clean_lab_df(excel_file: str, sheet_name: str) -> DataFrame:
    """Read and clean lab timetable from Excel."""
    dflab = pd.read_excel(excel_file, sheet_name=sheet_name, header=61)
    clean_dflab = dflab.loc[:, ~dflab.columns.str.contains('^Unnamed')]
    clean_dflab = clean_dflab.dropna(subset=['Lab'])
    clean_dflab = clean_dflab.fillna("NIL")
    return clean_dflab

