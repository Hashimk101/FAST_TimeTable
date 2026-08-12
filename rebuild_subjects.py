import sqlite3
import os
from sheets_subject_extractor import extract_subjects_and_batches_from_api

DB_FILE = "subjects.db"

def rebuild_subjects_db():
    print(f"Rebuilding {DB_FILE} from live Google Sheets API data...")

    # Extract live data from Google Sheets API
    legend_batches, unique_subjects, batch_subject_links = extract_subjects_and_batches_from_api()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Destroy previous database tables completely
    cursor.execute("DROP TABLE IF EXISTS batch_subjects;")
    cursor.execute("DROP TABLE IF EXISTS subjects;")
    cursor.execute("DROP TABLE IF EXISTS batches;")

    # 1. Create Batches Table
    cursor.execute("""
        CREATE TABLE batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            color_hex TEXT NOT NULL
        );
    """)

    # 2. Create Subjects Table
    cursor.execute("""
        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            short_name TEXT NOT NULL
        );
    """)

    # 3. Create Batch_Subjects Mapping Table
    cursor.execute("""
        CREATE TABLE batch_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE CASCADE,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
            UNIQUE(batch_id, subject_id)
        );
    """)

    # --- FUZZY MATCHING SYNC ---
    # Fetch canonical, typo-corrected subjects from uni_timetable.db
    canonical_conn = sqlite3.connect('uni_timetable.db')
    canonical_cursor = canonical_conn.cursor()
    try:
        canonical_cursor.execute("SELECT DISTINCT SUBJECT FROM timetable")
        canonical_subjects = [row[0] for row in canonical_cursor.fetchall()]
    except sqlite3.OperationalError:
        canonical_subjects = [] # DB might not exist yet if run out of order
    canonical_conn.close()

    import difflib
    corrected_unique_subjects = {}
    for name, short in unique_subjects.items():
        if name not in canonical_subjects and canonical_subjects:
            matches = difflib.get_close_matches(name, canonical_subjects, n=1, cutoff=0.85)
            if matches:
                print(f"  [FUZZY SYNC] '{name}' -> '{matches[0]}'")
                name = matches[0]
        # Keep the shortest 'short_name' if there are multiple due to merge
        if name in corrected_unique_subjects:
            if len(short) < len(corrected_unique_subjects[name]):
                corrected_unique_subjects[name] = short
        else:
            corrected_unique_subjects[name] = short

    corrected_batch_subject_links = set()
    for batch_name, subject_name in batch_subject_links:
        if subject_name not in canonical_subjects and canonical_subjects:
            matches = difflib.get_close_matches(subject_name, canonical_subjects, n=1, cutoff=0.85)
            if matches:
                subject_name = matches[0]
        corrected_batch_subject_links.add((batch_name, subject_name))
    # ---------------------------

    # Insert Batches in legend order
    batch_name_to_id = {}
    for batch in legend_batches:
        cursor.execute("INSERT INTO batches (name, color_hex) VALUES (?, ?)", (batch['name'], batch['hex']))
        batch_name_to_id[batch['name']] = cursor.lastrowid

    # Insert Subjects
    subject_name_to_id = {}
    for name, short in corrected_unique_subjects.items():
        cursor.execute("INSERT INTO subjects (name, short_name) VALUES (?, ?)", (name, short))
        subject_name_to_id[name] = cursor.lastrowid

    # Insert Batch-Subject Links
    inserted_links = 0
    for batch_name, subject_name in corrected_batch_subject_links:
        batch_id = batch_name_to_id.get(batch_name)
        subject_id = subject_name_to_id.get(subject_name)

        if batch_id and subject_id:
            try:
                cursor.execute("INSERT OR IGNORE INTO batch_subjects (batch_id, subject_id) VALUES (?, ?)", (batch_id, subject_id))
                inserted_links += 1
            except sqlite3.IntegrityError:
                pass

    conn.commit()
    conn.close()

    print(f"\nSuccessfully rebuilt {DB_FILE}:")
    print(f"  - Batches: {len(batch_name_to_id)}")
    print(f"  - Unique Subjects: {len(subject_name_to_id)}")
    print(f"  - Batch-Subject Mappings: {inserted_links}")

if __name__ == "__main__":
    rebuild_subjects_db()
