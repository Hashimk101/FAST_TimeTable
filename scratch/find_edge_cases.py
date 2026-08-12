import sqlite3

db = sqlite3.connect('uni_timetable.db')
cursor = db.cursor()

print("--- 1. BATCH NAMES WITH WEIRD CHARACTERS OR UNUSUAL FORMATS ---")
cursor.execute("SELECT DISTINCT BATCH FROM timetable WHERE BATCH NOT LIKE 'BS %' AND BATCH NOT LIKE 'MS %' AND BATCH NOT LIKE '%Repeat%'")
print(cursor.fetchall())

print("\n--- 2. SECTIONS WITH UNUSUAL FORMATS ---")
# Normal sections are A-J, CS-A, AI-A, etc. Let's look for long ones or weird chars
cursor.execute("SELECT DISTINCT SECTION FROM timetable WHERE length(SECTION) > 6")
print(cursor.fetchall())

print("\n--- 3. ROOM NAMES WITH WEIRD FORMATS ---")
cursor.execute("SELECT DISTINCT CLASSROOM FROM timetable WHERE length(CLASSROOM) > 10")
print(cursor.fetchall())

print("\n--- 4. SUBJECTS WITH UNUSUAL FORMATS (e.g. no spaces, very long, weird chars) ---")
cursor.execute("SELECT DISTINCT SUBJECT FROM timetable WHERE SUBJECT LIKE '%(%' OR SUBJECT LIKE '%/%' OR length(SUBJECT) > 30")
for row in cursor.fetchall()[:10]:
    print(row)

print("\n--- 5. TIMETABLE CLASHES (Same class, same room, same time, multiple entries) ---")
cursor.execute("""
    SELECT DAY, START_TIME, CLASSROOM, COUNT(*) 
    FROM timetable 
    GROUP BY DAY, START_TIME, CLASSROOM 
    HAVING COUNT(*) > 1
""")
for row in cursor.fetchall()[:5]:
    print(row)

db.close()
