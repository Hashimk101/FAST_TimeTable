import sqlite3
import json
import base64
import os
import re
import time
from datetime import datetime, timezone

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
        # Source of truth: Actual schedules in uni_timetable.db and uni_timetable_lab.db
        repeat_dict = {}
        
        # Load known metadata (ids, short_names) from subjects.db
        subject_meta = {}
        cursor.execute("SELECT id, name, short_name FROM subjects")
        for sid, sname, short in cursor.fetchall():
            if sname and sname.strip():
                subject_meta[sname.strip().lower()] = {
                    "id": sid, 
                    "name": sname.strip(), 
                    "short_name": (short or sname).strip()
                }

        # Also find any subjects explicitly mapped to repeat batch in subjects.db
        cursor.execute("""
            SELECT s.id, s.name, s.short_name
            FROM subjects s
            JOIN batch_subjects bs ON s.id = bs.subject_id
            JOIN batches b ON bs.batch_id = b.id
            WHERE b.name LIKE '%Repeat%'
        """)
        for sid, sname, short in cursor.fetchall():
            if sname and sname.strip():
                key = sname.strip().lower()
                repeat_dict[key] = {
                    "id": sid,
                    "name": sname.strip(),
                    "short_name": (short or sname).strip(),
                    "sections": set()
                }

        # Extract actual repeat subjects and sections from both timetable databases
        for db_path in [COURSE_DB, LAB_DB]:
            if not os.path.exists(db_path):
                continue
            with sqlite3.connect(db_path) as t_conn:
                t_cur = t_conn.cursor()
                t_cur.execute("""
                    SELECT DISTINCT SUBJECT, SECTION 
                    FROM timetable 
                    WHERE BATCH LIKE '%Repeat%' AND SUBJECT IS NOT NULL
                """)
                for sname, sec in t_cur.fetchall():
                    sname_clean = (sname or '').strip()
                    sec_clean = (sec or '').strip()
                    if not sname_clean or sname_clean.lower() in {'room', 'lab', 'nil', 'none'}:
                        continue
                    
                    key = sname_clean.lower()
                    if key not in repeat_dict:
                        meta = subject_meta.get(key, {})
                        repeat_dict[key] = {
                            "id": meta.get("id", len(repeat_dict) + 1000),
                            "name": meta.get("name", sname_clean),
                            "short_name": meta.get("short_name", sname_clean),
                            "sections": set()
                        }
                    
                    if sec_clean:
                        repeat_dict[key]["sections"].add(sec_clean)

        repeats = []
        for item in sorted(repeat_dict.values(), key=lambda x: x["name"]):
            repeats.append({
                "id": item["id"],
                "name": item["name"],
                "short_name": item["short_name"],
                "sections": sorted(list(item["sections"]))
            })

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

    # 6. Generate Version Manifest
    version_info = {
        "version": int(time.time()),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    version_path = os.path.join(OUTPUT_DIR, 'version.json')
    with open(version_path, 'w') as f:
        json.dump(version_info, f, indent=2)
    print(f"Generated version.json (v={version_info['version']})")

if __name__ == '__main__':
    generate_static_data()
