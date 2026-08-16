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
days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


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
                BATCH TEXT,
                STATUS TEXT,

                UNIQUE(DAY, {location_column}, START_TIME) -- to avoid overlapping classes in the same classroom just in case the timetable is incorrect
                )
                ''')
    
    crsr.execute("DELETE FROM timetable")

    crsr.execute(''' CREATE INDEX IF NOT EXISTS idx_day_section ON timetable (DAY, SECTION, SUBJECT) ''')
    conn.commit()
    conn.close()

def correct_typos_in_db(db_name: str = 'uni_timetable.db'):
    import difflib
    from collections import Counter
    conn = sqlite3.connect(db_name)
    crsr = conn.cursor()
    
    # Get all subjects
    crsr.execute("SELECT SUBJECT FROM timetable")
    rows = crsr.fetchall()
    if not rows:
        conn.close()
        return
        
    subjects = [r[0] for r in rows]
    counts = Counter(subjects)
    
    # Canonical subjects are those appearing 3 or more times
    canonical = [s for s, c in counts.items() if c >= 3]
    if not canonical:
        conn.close()
        return
        
    corrections = {}
    for s, c in counts.items():
        if c <= 2:
            matches = difflib.get_close_matches(s, canonical, n=1, cutoff=0.85)
            if matches:
                corrections[s] = matches[0]
                
    # Apply corrections
    for old_s, new_s in corrections.items():
        print(f"  [FUZZY] Correcting typo in DB '{db_name}': '{old_s}' -> '{new_s}'")
        crsr.execute("UPDATE timetable SET SUBJECT = ? WHERE SUBJECT = ?", (new_s, old_s))
        
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

            for single_subject in str(subject).split(" | "):
                single_subject = single_subject.strip()
                if not single_subject or single_subject == "NIL":
                    continue
                    
                has_custom_time = check_if_time_in_subject(single_subject)
                if is_unnamed_col and not has_custom_time:
                    continue

                entry = {
                    'location': location,
                    'time_slot': time_slot,
                    'subject': single_subject,
                }
                timetable_list.append(entry)

    return timetable_list

STATUS_PATTERN = re.compile(
    r'[\s\-_\(\[]*\b(Cancell?ed|Cancel|Resch(?:edul(?:ed|e)|udl(?:ed|e)|ed|uled)?|Re-?sch(?:edul(?:ed|e))?|Reserved?|Postponed?)\b[\s\-_\)\]]*',
    re.IGNORECASE
)

def extract_status(text: str) -> tuple:
    """
    Extract status keyword (Cancelled, Rescheduled, Reserved, Postponed) from text
    and return (normalized_status, text_without_status).
    """
    match = STATUS_PATTERN.search(text)
    if not match:
        return None, text
    raw = match.group(1).lower()
    if raw.startswith('canc'):
        status = 'Cancelled'
    elif raw.startswith('resch') or raw.startswith('re-sch'):
        status = 'Rescheduled'
    elif raw.startswith('reserv'):
        status = 'Reserved'
    elif raw.startswith('postpon'):
        status = 'Postponed'
    else:
        status = raw.capitalize()

    start, end = match.span()
    cleaned = (text[:start] + ' ' + text[end:]).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'\(\s*\)', '', cleaned).strip()
    if '(' in cleaned and ')' not in cleaned:
        cleaned += ')'
    return status, cleaned

def clean_section(raw_section: str) -> str:
    '''
    Cleans the raw section string extracted from the Google Sheet.
    Handles all known formatting patterns:
      1. "CS-C, 24"          -> "CS-C"       (strip batch year)
      2. "CS-C  D-314"       -> "CS-C"       (strip room code leaked in)
      3. "DS-A  in Room no. D-405" -> "DS-A" (strip room redirect text)
      4. "AI-A, 22 ReSch"    -> "AI-A"       (strip batch + ReSch)
      5. "CS-B, G-I"         -> "CS-B, G-I"  (keep group identifiers)
      6. "SE-A Audi (G-Flr, Blk-D" -> "SE-A" (strip venue info)
      7. "CS-C, 25 Cancelled\nOOP Lab..." -> "CS-C" (strip multiline junk)
    '''
    section = raw_section.strip()
    if not section:
        return section

    # Remove newlines and everything after them (multiline junk)
    if '\n' in section:
        section = section.split('\n')[0].strip()

    # Remove "in Room no. XXX" suffixes
    in_room_match = re.search(r'\s+in\s+Room\s+no\.\s*\S+', section, re.IGNORECASE)
    if in_room_match:
        section = section[:in_room_match.start()].strip()

    # Remove ReSch / Cancelled / Reserved / Postponed / "on for ..." suffixes
    section = re.sub(
        r'\s+(Re-?sch(?:edul(?:ed|e)|udl(?:ed|e)|ed|uled)?|Cancell?ed|Cancel|Reserved?|Postponed?|on for .*)$',
        '',
        section,
        flags=re.IGNORECASE
    ).strip()

    # Remove "Audi ..." or venue info after the section code
    audi_match = re.search(r'\s+Audi\s', section)
    if audi_match:
        section = section[:audi_match.start()].strip()

    # Now handle the comma-separated part.
    # Valid: "CS-B, G-I", "DS, Gp-II", "DS-A, Gp-I"
    # Invalid: "CS-C, 24", "AI-A, 22", "CS-A, 25"
    if ',' in section:
        parts = section.split(',', 1)
        after_comma = parts[1].strip()
        # If the part after the comma is a 2-digit number (batch year), strip it
        if re.match(r'^\d{2}$', after_comma):
            section = parts[0].strip()
        # If it starts with a 2-digit number followed by space+junk, strip it
        elif re.match(r'^\d{2}\s', after_comma):
            section = parts[0].strip()
        # Otherwise keep it (it's a group identifier like G-I, Gp-II)

    # Remove trailing room codes like "D-314", "D-414", "A-104"
    # These are room patterns: single letter + dash + digits
    section = re.sub(r'\s+[A-Z]-\d{3,4}$', '', section).strip()

    # Reject if the remaining string is just a discipline name without a section
    bare_disciplines = {'CS', 'SE', 'AI', 'DS', 'CY', 'AI/DS', 'AI/DS/SE'}
    if section in bare_disciplines:
        return ""

    return section


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
    text = subject_with_section.strip()
    
    # Fix missing space before '(' — "Elective(SE-A)" → "Elective (SE-A)"
    text = re.sub(r'(\w)\(', r'\1 (', text)
    
    if '(' in text:
        parts = text.split('(', 1)
        subject = parts[0].strip()
        inside = parts[1]
        if ')' in inside:
            section = inside.split(')', 1)[0].strip()
        else:
            section = inside.strip()
        return subject, clean_section(section)
    
    # Fallback 1: No '(' but text ends with section-like pattern
    # e.g. "PF CS-A" → subject="PF", section="CS-A"
    match = re.match(r'^(.+?)\s+([A-Z]{2,4}-[A-Z]\w*)$', text)
    if match:
        return match.group(1).strip(), clean_section(match.group(2).strip())
    
    # Last resort: full text as subject, empty section
    return text, ""

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
    return subject.strip(), clean_section(section.strip()), time_slot.strip()


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
        
        # Ensure BATCH column exists
        try:
            crsr.execute("ALTER TABLE timetable ADD COLUMN BATCH TEXT")
        except sqlite3.OperationalError:
            pass # Column already exists

        # Ensure STATUS column exists
        try:
            crsr.execute("ALTER TABLE timetable ADD COLUMN STATUS TEXT")
        except sqlite3.OperationalError:
            pass # Column already exists

        SKIP_PATTERNS = [
            r'^[A-Z]-\d{3}',              # Room names: D-301, C-405
            r'^P\s+R\s+A\s+Y\s+E\s+R',   # PRAYER BREAK
            r'^Tutorial\s',                # Tutorial Batch 26
            r'^EE$',                       # Standalone EE
            r'^FSM$',                      # Explicitly drop FSM
            r'^PPIT\s*Seminar$'            # Explicitly drop PPIT Seminar
        ]
        skip_words = {'prayer', 'break', 'tutorial', 'fsm', 'ppit seminar'}

        timetable_list = get_list_of_dicts_from_df(clean_df, location_col)

        for entry in timetable_list:
            raw_subj = entry['subject'].strip()
            if any(re.match(p, raw_subj) for p in SKIP_PATTERNS):
                continue
            if raw_subj.lower() in skip_words:
                continue

            # 1. Extract batch from subject if present (e.g. "Comp Net (CS-D) Cancelled [BS 24 CS]")
            batch = None
            match = re.search(r'\[(.*?)\]$', entry['subject'])
            if match:
                batch = match.group(1).strip()
                entry['subject'] = re.sub(r'\s*\[.*?\]$', '', entry['subject']).strip()

            # 2. Extract Rescheduled/Cancelled/Reserved/Postponed status now that [batch] tag is removed
            status, entry['subject'] = extract_status(entry['subject'])
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

            # Assign to repeat courses if no section and no batch
            if not entry.get('section') and not batch:
                batch = 'BS Repeat Courses'

            # ... rest of the insertion code ...
            crsr.execute(f'''
                INSERT OR IGNORE INTO timetable (DAY, START_TIME, END_TIME, SUBJECT, {db_location_col}, SECTION, BATCH, STATUS)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (day, entry['start_time'], entry['end_time'], entry['subject'], entry['location'], entry['section'], batch, status))

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
    result = sheet.get(
        spreadsheetId=spreadsheet_id, 
        ranges=[sheet_name],
        includeGridData=True
    ).execute()
    sheets = result.get('sheets', [])
    if sheets:
        return sheets[0].get('data', [])[0].get('rowData', [])
    return []

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


def fetch_timetable_for_section(db_name: str, section: str, list_of_subs: list, batch: str = None) -> list:
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

            # Build query
            if batch:
                query = f'''
                    SELECT * FROM timetable
                    WHERE DAY = ?
                    AND SECTION = ?
                    AND SUBJECT IN ({placeholders})
                    AND BATCH = ?
                '''
                params = [day, section] + list_of_subs + [batch]
            else:
                query = f'''
                    SELECT * FROM timetable
                    WHERE DAY = ?
                    AND SECTION = ?
                    AND SUBJECT IN ({placeholders})
                '''
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

