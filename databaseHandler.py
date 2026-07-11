import sqlite3
import pandas as pd
from pandas import DataFrame, Series
import numpy as np
import os.path
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import sheets_to_df

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
    
    crsr.execute("DELETE FROM timetable")

    crsr.execute(''' CREATE INDEX IF NOT EXISTS idx_day_section ON timetable (DAY, SECTION, SUBJECT) ''')
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

            # 1. Skip empty cells
            if subject == "NIL":
                continue

            # 2. Safety Check for Unnamed columns
            # If the column has no header (Unnamed) AND the subject text
            # does NOT have a custom time inside it (e.g. "Civics... 02:00"),
            # then it is likely garbage data. Skip it.
            is_unnamed_col = "Unnamed" in str(time_slot)
            has_custom_time = check_if_time_in_subject(str(subject))

            if is_unnamed_col and not has_custom_time:
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
    if not second.strip():
        return False
    return '-' in second and ':' in second

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
    match = re.search(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})', time_slot)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    
    # Fallback to original split if regex doesn't match
    parts = time_slot.split('-')
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return time_slot, time_slot

def insert_timetable(clean_df: DataFrame, day: str, db_name: str = 'uni_timetable.db',
                     location_col: str = 'Room', db_location_col: str = 'CLASSROOM') -> None:
    conn = sqlite3.connect(db_name)
    try:
        crsr = conn.cursor()

        timetable_list = get_list_of_dicts_from_df(clean_df, location_col)

        for entry in timetable_list:
            # Case 1: Time is in the text (like Civics 02:00-03:45)
            if check_if_time_in_subject(entry['subject']):
                subject, section, time_slot = separate_time_and_section_from_subject(entry['subject'])
                entry['subject'] = subject
                entry['section'] = section
                entry['time_slot'] = time_slot

            # Case 2: Time is in the header (Standard classes)
            else:
                # SAFETY CHECK: If we somehow got here with an Unnamed header, skip to avoid crash
                if "Unnamed" in str(entry['time_slot']):
                    continue

                subject, section = separate_subject_and_section(entry['subject'])
                entry['subject'] = subject
                entry['section'] = section

            # Now it is safe to split
            start_time, end_time = separate_time_slot(entry['time_slot'])
            entry['start_time'] = start_time
            entry['end_time'] = end_time

            # ... rest of the insertion code ...
            crsr.execute(f'''
                INSERT OR IGNORE INTO timetable (DAY, START_TIME, END_TIME, SUBJECT, {db_location_col}, SECTION)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (day, entry['start_time'], entry['end_time'], entry['subject'], entry['location'], entry['section']))

        conn.commit()
    finally:
        conn.close()


def get_sheets_service():
    scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', scopes)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('sheets', 'v4', credentials=creds)

def get_raw_sheet(service, spreadsheet_id, sheet_name):
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=spreadsheet_id, range=sheet_name).execute()
    return result.get('values', [])

def read_and_clean_classroom_df(service, spreadsheet_id: str, sheet_name: str) -> DataFrame:
    """Read and clean classroom timetable from Google Sheets."""
    raw_values = get_raw_sheet(service, spreadsheet_id, sheet_name)
    return sheets_to_df.sheets_to_classroom_df(raw_values)

def read_and_clean_lab_df(service, spreadsheet_id: str, sheet_name: str) -> DataFrame:
    """Read and clean lab timetable from Google Sheets."""
    raw_values = get_raw_sheet(service, spreadsheet_id, sheet_name)
    return sheets_to_df.sheets_to_lab_df(raw_values)



class subjectEntry:
    def __init__(self, starttime: str, endtime: str, subject: str, location: str):
        self.starttime = starttime
        self.endtime = endtime
        self.subject = subject
        self.location = location
    def __repr__(self):
        return f"subjectEntry(starttime={self.starttime}, endtime={self.endtime}, subject={self.subject}, location={self.location})"
    def display(self):
        print(f"{self.starttime} - {self.endtime} : {self.subject} at {self.location}")

    def __str__(self):
        return f"{self.starttime}-{self.endtime}: {self.subject} @ {self.location}"


def fetch_timetable_for_section(db_name: str, section: str, list_of_subs: list) -> list:
    # 0 to 4 -> Monday to Friday
    list_of_days_in_timetable = []

    # Return empty structure if no subjects provided
    if not list_of_subs:
        return [[] for _ in range(5)] # Assuming 5 days

    # Prepare the placeholder string (e.g., "?, ?, ?") for the SQL IN clause
    placeholders = ', '.join('?' for _ in list_of_subs)

    with sqlite3.connect(db_name) as conn:
        cursor = conn.cursor()

        for day in days_of_week:
            list_of_subs_per_day = []

            # 1. THE INDEX (DAY, SECTION, SUBJECT) handles the WHERE clause efficiently.
            query = f'''
                SELECT * FROM timetable
                WHERE DAY = ?
                AND SECTION = ?
                AND SUBJECT IN ({placeholders})
            '''

            # Combine parameters: Day, Section, then the list of subjects
            params = [day, section] + list_of_subs

            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            def parse_time(time_str):
                try:
                    h, m = map(int, time_str.split(':'))
                    if 1 <= h <= 7:
                        h += 12
                    return h * 60 + m
                except Exception:
                    return 0
                    
            rows.sort(key=lambda r: parse_time(r[2]))

            for row in rows:
                # row[2]=start, row[3]=end, row[4]=subject, row[5]=location
                subval = subjectEntry(
                    starttime=row[2],
                    endtime=row[3],
                    subject=row[4],
                    location=row[5]
                )
                list_of_subs_per_day.append(subval)

            list_of_days_in_timetable.append(list_of_subs_per_day)

    return list_of_days_in_timetable

