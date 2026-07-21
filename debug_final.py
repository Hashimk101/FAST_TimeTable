import sqlite3
conn = sqlite3.connect('uni_timetable.db')
cur = conn.cursor()
cur.execute("SELECT * FROM timetable WHERE CLASSROOM='D-506' AND DAY='Tuesday'")
for r in cur.fetchall():
    print(r)
conn.close()
