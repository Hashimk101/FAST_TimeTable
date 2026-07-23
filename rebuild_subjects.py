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

    # Insert Batches in legend order
    batch_name_to_id = {}
    for batch in legend_batches:
        cursor.execute("INSERT INTO batches (name, color_hex) VALUES (?, ?)", (batch['name'], batch['hex']))
        batch_name_to_id[batch['name']] = cursor.lastrowid

    # Insert Subjects
    subject_name_to_id = {}
    for name, short in unique_subjects.items():
        cursor.execute("INSERT INTO subjects (name, short_name) VALUES (?, ?)", (name, short))
        subject_name_to_id[name] = cursor.lastrowid

    # Insert Batch-Subject Links
    inserted_links = 0
    for batch_name, subject_name in batch_subject_links:
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
