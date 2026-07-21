import sqlite3

# Check what sections exist for Pak Studies specifically
conn = sqlite3.connect('uni_timetable.db')
cur = conn.cursor()

print("=== Pak Studies sections ===")
cur.execute("SELECT DISTINCT SECTION FROM timetable WHERE SUBJECT LIKE '%Pak%'")
for r in cur.fetchall():
    print(f"  '{r[0]}'")

print("\n=== All Pak Studies rows ===")
cur.execute("SELECT * FROM timetable WHERE SUBJECT LIKE '%Pak%' ORDER BY SECTION")
for r in cur.fetchall():
    print(r)

print("\n=== Sections with 'in Room' ===")
cur.execute("SELECT * FROM timetable WHERE SECTION LIKE '%in Room%'")
for r in cur.fetchall():
    print(r)

print("\n=== Sections with room codes (D-xxx) embedded ===")
cur.execute("SELECT DISTINCT SECTION FROM timetable WHERE SECTION LIKE '%D-%' AND SECTION NOT LIKE 'DS%' AND SECTION NOT LIKE '%DS%'")
for r in cur.fetchall():
    print(f"  '{r[0]}'")

conn.close()

# Lab DB
conn2 = sqlite3.connect('uni_timetable_lab.db')
cur2 = conn2.cursor()

print("\n=== LAB: OS Lab for CS-C (exact) ===")
cur2.execute("SELECT * FROM timetable WHERE SUBJECT='OS Lab' AND SECTION LIKE '%CS-C%'")
for r in cur2.fetchall():
    print(r)

print("\n=== LAB: Sections with room codes embedded ===")
cur2.execute("SELECT DISTINCT SECTION FROM timetable WHERE SECTION LIKE '%D-%' AND SECTION NOT LIKE 'DS%'")
for r in cur2.fetchall():
    print(f"  '{r[0]}'")

print("\n=== LAB: Sections with embedded info (ReSch, Cancelled, etc.) ===")
cur2.execute("SELECT DISTINCT SECTION FROM timetable WHERE SECTION LIKE '%ReSch%' OR SECTION LIKE '%Cancel%' OR SECTION LIKE '%Exam%'")
for r in cur2.fetchall():
    print(f"  '{r[0]}'")

conn2.close()
