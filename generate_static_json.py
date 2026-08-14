import sqlite3
import json
import base64
import os
import re

SUBJECTS_DB = 'subjects.db'
COURSE_DB = 'uni_timetable.db'
LAB_DB = 'uni_timetable_lab.db'
OUTPUT_DIR = os.path.join('frontend', 'data')

DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

def encode_data(data):
    json_str = json.dumps(data, separators=(',', ':'))
    reversed_str = json_str[::-1]
    return base64.b64encode(reversed_str.encode('utf-8')).decode('utf-8')

def sanitize_filename(name):
    if not name:
        return ""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name.strip())

def parse_time(time_str):
    try:
        h, m = map(int, time_str.split(':'))
        if 1 <= h <= 7:
            h += 12
        return h * 60 + m
    except Exception:
        return 0

def generate_static_data():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    schedules_dir = os.path.join(OUTPUT_DIR, 'schedules')
    os.makedirs(schedules_dir, exist_ok=True)

    print("Generating static binary data files...")

    # 1. Batches
    with sqlite3.connect(SUBJECTS_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, color_hex FROM batches ORDER BY id ASC")
        batches_rows = cursor.fetchall()
        batches = [{"id": r[0], "name": r[1], "color_hex": r[2]} for r in batches_rows]
        
        with open(os.path.join(OUTPUT_DIR, 'batches.bin'), 'w') as f:
            f.write(encode_data(batches))
        print(f"Generated batches.bin ({len(batches)} batches)")

        # 2. Subjects by Batch & All Subjects
        cursor.execute("SELECT id, name, short_name FROM subjects ORDER BY name ASC")
        all_subjects_rows = cursor.fetchall()
        all_subjects = [{"id": r[0], "name": r[1], "short_name": r[2]} for r in all_subjects_rows]

        # Map batch_id to subjects
        cursor.execute("""
            SELECT b.name, s.id, s.name, s.short_name
            FROM batch_subjects bs
            JOIN batches b ON bs.batch_id = b.id
            JOIN subjects s ON bs.subject_id = s.id
            ORDER BY s.name ASC
        """)
        batch_subs_rows = cursor.fetchall()
        subjects_by_batch = {}
        for r in batch_subs_rows:
            batch_name = r[0]
            if batch_name not in subjects_by_batch:
                subjects_by_batch[batch_name] = []
            subjects_by_batch[batch_name].append({"id": r[1], "name": r[2], "short_name": r[3]})

        subjects_by_batch["ALL"] = all_subjects

        with open(os.path.join(OUTPUT_DIR, 'subjects.bin'), 'w') as f:
            f.write(encode_data(subjects_by_batch))
        print(f"Generated subjects.bin")

        # 3. Elective subjects
        cursor.execute("""
            SELECT DISTINCT s.id, s.name, s.short_name
            FROM subjects s
            JOIN batch_subjects bs ON s.id = bs.subject_id
            JOIN batches b ON bs.batch_id = b.id
            WHERE b.name LIKE '%Elective%'
            ORDER BY s.name ASC
        """)
        electives = [{"id": r[0], "name": r[1], "short_name": r[2]} for r in cursor.fetchall()]
        with open(os.path.join(OUTPUT_DIR, 'electives.bin'), 'w') as f:
            f.write(encode_data(electives))
        print(f"Generated electives.bin ({len(electives)} electives)")

        # 4. Repeat subjects with sections
        cursor.execute("ATTACH DATABASE ? AS uni", (COURSE_DB,))
        cursor.execute("ATTACH DATABASE ? AS lab", (LAB_DB,))
        cursor.execute("""
            SELECT DISTINCT s.id, s.name, s.short_name, t.SECTION
            FROM subjects s
            JOIN batch_subjects bs ON s.id = bs.subject_id
            JOIN batches b ON bs.batch_id = b.id
            LEFT JOIN (
                SELECT SUBJECT, BATCH, SECTION FROM uni.timetable
                UNION
                SELECT SUBJECT, BATCH, SECTION FROM lab.timetable
            ) t ON t.SUBJECT = s.name AND t.BATCH = b.name
            WHERE b.name LIKE '%Repeat%'
            ORDER BY s.name ASC, t.SECTION ASC
        """)
        repeat_rows = cursor.fetchall()
        cursor.execute("DETACH DATABASE uni")
        cursor.execute("DETACH DATABASE lab")
        
        repeat_dict = {}
        for r in repeat_rows:
            sid, sname, short, section = r[0], r[1], r[2], r[3]
            if sid not in repeat_dict:
                repeat_dict[sid] = {"id": sid, "name": sname, "short_name": short, "sections": []}
            if section is not None and section not in repeat_dict[sid]["sections"]:
                repeat_dict[sid]["sections"].append(section)
                
        repeats = list(repeat_dict.values())
        with open(os.path.join(OUTPUT_DIR, 'repeats.bin'), 'w') as f:
            f.write(encode_data(repeats))
        print(f"Generated repeats.bin ({len(repeats)} repeat subjects)")

    # 5. Schedules Generation (Combining Theory + Lab)
    # Collect all (BATCH, SECTION) combinations from both databases
    combos = set()

    for db_path in [COURSE_DB, LAB_DB]:
        if not os.path.exists(db_path):
            continue
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT BATCH, SECTION FROM timetable WHERE BATCH IS NOT NULL")
            for row in cursor.fetchall():
                b, s = row[0], row[1]
                if b and b.startswith('MS'):
                    combos.add((b, ''))
                elif b:
                    combos.add((b, s or ''))

    print(f"Processing {len(combos)} batch/section combinations for schedules...")

    count = 0
    for batch_val, section_val in combos:
        # Build merged 5-day schedule
        timetable_5days = []

        for day in DAYS_OF_WEEK:
            day_entries = []

            for db_path, loc_col in [(COURSE_DB, 'CLASSROOM'), (LAB_DB, 'LAB')]:
                if not os.path.exists(db_path):
                    continue
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    if str(batch_val).startswith('MS'):
                        cursor.execute(f"""
                            SELECT START_TIME, END_TIME, SUBJECT, {loc_col}, STATUS
                            FROM timetable
                            WHERE DAY = ? AND BATCH = ?
                        """, (day, batch_val))
                    elif batch_val:
                        cursor.execute(f"""
                            SELECT START_TIME, END_TIME, SUBJECT, {loc_col}, STATUS
                            FROM timetable
                            WHERE DAY = ? AND SECTION = ? AND BATCH = ?
                        """, (day, section_val, batch_val))
                    else:
                        cursor.execute(f"""
                            SELECT START_TIME, END_TIME, SUBJECT, {loc_col}, STATUS
                            FROM timetable
                            WHERE DAY = ? AND SECTION = ?
                        """, (day, section_val))

                    for row in cursor.fetchall():
                        day_entries.append({
                            "start_time": row[0],
                            "end_time": row[1],
                            "subject": row[2],
                            "location": row[3],
                            "status": row[4]
                        })

            # Sort by start_time
            day_entries.sort(key=lambda x: parse_time(x["start_time"]))
            timetable_5days.append(day_entries)

        # File naming convention:
        # e.g., batch_val = "BS 25 CS", section_val = "CS-A" -> "BS_25_CS__CS-A.bin"
        batch_slug = sanitize_filename(batch_val)
        section_slug = sanitize_filename(section_val)
        file_name = f"{batch_slug}__{section_slug}.bin"
        file_path = os.path.join(schedules_dir, file_name)

        with open(file_path, 'w') as f:
            f.write(encode_data(timetable_5days))
        count += 1

    print(f"Successfully generated {count} schedule binary files in {schedules_dir}!")

if __name__ == '__main__':
    generate_static_data()
