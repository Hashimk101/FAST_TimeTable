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

    # 1. Batches (Only BS batches)
    with sqlite3.connect(SUBJECTS_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, color_hex FROM batches WHERE name LIKE 'BS%' ORDER BY id ASC")
        batches_rows = cursor.fetchall()
        batches = [{"id": r[0], "name": r[1], "color_hex": r[2]} for r in batches_rows]
        
        with open(os.path.join(OUTPUT_DIR, 'batches.bin'), 'w') as f:
            f.write(encode_data(batches))
        print(f"Generated batches.bin ({len(batches)} batches)")

        # 2. Subjects by Batch & All Subjects
        cursor.execute("SELECT id, name, short_name FROM subjects ORDER BY name ASC")
        all_subjects_rows = cursor.fetchall()
        all_subjects = [{"id": r[0], "name": r[1], "short_name": r[2]} for r in all_subjects_rows]

        # Map batch_id to subjects (Only BS batches)
        cursor.execute("""
            SELECT b.name, s.id, s.name, s.short_name
            FROM batch_subjects bs
            JOIN batches b ON bs.batch_id = b.id
            JOIN subjects s ON bs.subject_id = s.id
            WHERE b.name LIKE 'BS%'
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

        # 3. Electives (Empty now that MS is dropped)
        with open(os.path.join(OUTPUT_DIR, 'electives.bin'), 'w') as f:
            f.write(encode_data([]))
        print(f"Generated electives.bin (0 electives)")

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
            cursor.execute("SELECT DISTINCT BATCH, SECTION FROM timetable WHERE BATCH LIKE 'BS%'")
            for row in cursor.fetchall():
                b, s = row[0], row[1]
                if b:
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
                    if batch_val and section_val:
                        cursor.execute(f"""
                            SELECT START_TIME, END_TIME, SUBJECT, {loc_col}, STATUS
                            FROM timetable
                            WHERE DAY = ? AND (SECTION = ? OR SECTION = '' OR SECTION IS NULL) AND BATCH = ?
                        """, (day, section_val, batch_val))
                    elif batch_val:
                        cursor.execute(f"""
                            SELECT START_TIME, END_TIME, SUBJECT, {loc_col}, STATUS
                            FROM timetable
                            WHERE DAY = ? AND (SECTION = '' OR SECTION IS NULL) AND BATCH = ?
                        """, (day, batch_val))
                    else:
                        cursor.execute(f"""
                            SELECT START_TIME, END_TIME, SUBJECT, {loc_col}, STATUS
                            FROM timetable
                            WHERE DAY = ? AND SECTION = ?
                        """, (day, section_val))

                    for row in cursor.fetchall():
                        if not row[0] or not row[1] or row[0] == row[1]:
                            continue
                        day_entries.append({
                            "start_time": row[0],
                            "end_time": row[1],
                            "subject": row[2],
                            "location": row[3],
                            "status": row[4]
                        })

            # Merge entries with exact same start_time, end_time, subject, status (e.g. concurrent lab subsections)
            merged_dict = {}
            for entry in day_entries:
                key = (entry["start_time"], entry["end_time"], entry["subject"], entry["status"])
                if key not in merged_dict:
                    merged_dict[key] = {
                        "start_time": entry["start_time"],
                        "end_time": entry["end_time"],
                        "subject": entry["subject"],
                        "locations": [entry["location"]] if entry.get("location") else [],
                        "status": entry["status"]
                    }
                else:
                    if entry.get("location") and entry["location"] not in merged_dict[key]["locations"]:
                        merged_dict[key]["locations"].append(entry["location"])

            merged_entries = []
            for item in merged_dict.values():
                loc_str = " | ".join(item["locations"]) if item["locations"] else ""
                merged_entries.append({
                    "start_time": item["start_time"],
                    "end_time": item["end_time"],
                    "subject": item["subject"],
                    "location": loc_str,
                    "status": item["status"]
                })

            # Sort by start_time
            merged_entries.sort(key=lambda x: parse_time(x["start_time"]))
            timetable_5days.append(merged_entries)

        # File naming convention:
        # e.g., batch_val = "BS 25 CS", section_val = "CS-A" -> "BS_25_CS__CS-A.bin"
        batch_slug = sanitize_filename(batch_val)
        section_slug = sanitize_filename(section_val)
        file_name = f"{batch_slug}__{section_slug}.bin"
        file_path = os.path.join(schedules_dir, file_name)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(encode_data(timetable_5days))
        count += 1

    print(f"Successfully generated {count} schedule binary files in {schedules_dir}!")

    
    # NEW: Generate Free Rooms Occupancy Map (Including Classroom & Lab Occupancy)
    print("Generating rooms.bin for Find Free Rooms...")
    rooms_data = {
        "rooms": [],
        "occupied": { d: {} for d in DAYS_OF_WEEK }
    }
    
    # 1. Collect Block C & D rooms from theory classrooms
    with sqlite3.connect(COURSE_DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT CLASSROOM FROM timetable WHERE (CLASSROOM LIKE 'C-%' OR CLASSROOM LIKE 'D-%') AND CLASSROOM IS NOT NULL")
        for r in cur.fetchall():
            room_code = r[0].strip()
            if room_code and room_code not in rooms_data["rooms"]:
                rooms_data["rooms"].append(room_code)

    # 2. Collect Block C & D rooms from lab locations (e.g. "Rawal 3-GPU (C-511)" -> "C-511")
    if os.path.exists(LAB_DB):
        with sqlite3.connect(LAB_DB) as conn:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT LAB FROM timetable WHERE LAB IS NOT NULL")
            for r in cur.fetchall():
                lab_str = r[0].strip()
                match = re.search(r'\b([CD]-\d{3})\b', lab_str, re.IGNORECASE)
                if match:
                    room_code = match.group(1).upper()
                    if room_code not in rooms_data["rooms"]:
                        rooms_data["rooms"].append(room_code)

    rooms_data["rooms"].sort()
    for r in rooms_data["rooms"]:
        for d in DAYS_OF_WEEK:
            rooms_data["occupied"][d][r] = []
            
    # 3. Populate theory occupancy
    with sqlite3.connect(COURSE_DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT DAY, CLASSROOM, START_TIME, END_TIME FROM timetable WHERE (CLASSROOM LIKE 'C-%' OR CLASSROOM LIKE 'D-%') AND START_TIME IS NOT NULL AND END_TIME IS NOT NULL AND START_TIME != '' AND END_TIME != ''")
        for day, room, start, end in cur.fetchall():
            room_code = (room or '').strip()
            if day in rooms_data["occupied"] and room_code in rooms_data["occupied"][day]:
                rooms_data["occupied"][day][room_code].append({"s": start, "e": end})

    # 4. Populate lab occupancy
    if os.path.exists(LAB_DB):
        with sqlite3.connect(LAB_DB) as conn:
            cur = conn.cursor()
            cur.execute("SELECT DAY, LAB, START_TIME, END_TIME FROM timetable WHERE LAB IS NOT NULL AND START_TIME IS NOT NULL AND END_TIME IS NOT NULL AND START_TIME != '' AND END_TIME != ''")
            for day, lab, start, end in cur.fetchall():
                lab_str = (lab or '').strip()
                match = re.search(r'\b([CD]-\d{3})\b', lab_str, re.IGNORECASE)
                if match:
                    room_code = match.group(1).upper()
                    if day in rooms_data["occupied"] and room_code in rooms_data["occupied"][day]:
                        rooms_data["occupied"][day][room_code].append({"s": start, "e": end})
            
    with open(os.path.join(OUTPUT_DIR, 'rooms.bin'), 'w') as f:
        f.write(encode_data(rooms_data))
    print(f"Generated rooms.bin ({len(rooms_data['rooms'])} rooms tracked)")

    # 6. Generate Version Manifest
    version_info = {
        "version": int(time.time()),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    version_path = os.path.join(OUTPUT_DIR, 'version.json')
    with open(version_path, 'w', encoding='utf-8') as f:
        json.dump(version_info, f, indent=2)
    print(f"Generated version.json (v={version_info['version']})")

if __name__ == '__main__':
    generate_static_data()
