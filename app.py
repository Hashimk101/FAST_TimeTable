from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from databaseHandler import fetch_timetable_for_section

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUBJECTS_DB = os.path.join(BASE_DIR, "subjects.db")
COURSE_DB = os.path.join(BASE_DIR, "uni_timetable.db")
LAB_DB = os.path.join(BASE_DIR, "uni_timetable_lab.db")

# Route to serve the main frontend HTML
@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/subjects', methods=['GET'])
def get_subjects():
    """Returns a list of all subjects from the subjects.db"""
    try:
        with sqlite3.connect(SUBJECTS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, short_name FROM subjects ORDER BY name ASC")
            rows = cursor.fetchall()
            
            subjects = [{"id": row[0], "name": row[1], "short_name": row[2]} for row in rows]
            return jsonify({"status": "success", "data": subjects})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/timetable', methods=['POST'])
def get_timetable():
    """
    Accepts JSON like: {"course": "SE", "section": "A", "subjects": ["Civics", "OS"]}
    Returns the timetable structure.
    """
    data = request.json
    course = data.get('course', '').strip().upper()
    section = data.get('section', '').strip().upper()
    subjects = data.get('subjects', [])
    
    if not course or not section or not subjects:
        return jsonify({"status": "error", "message": "Missing course, section, or subjects"}), 400
        
    cosec = f"{course}-{section}"
    
    try:
        raw_timetable_course = fetch_timetable_for_section(COURSE_DB, cosec, subjects)
        raw_timetable_lab = fetch_timetable_for_section(LAB_DB, cosec, subjects)
        
        raw_timetable = []
        for i in range(5):
            merged = raw_timetable_course[i] + raw_timetable_lab[i]
            def parse_time(time_str):
                try:
                    h, m = map(int, time_str.split(':'))
                    if 1 <= h <= 7:
                        h += 12
                    return h * 60 + m
                except Exception:
                    return 0
            merged.sort(key=lambda r: parse_time(r.starttime))
            raw_timetable.append(merged)
        
        # Convert objects to dicts for JSON serialization
        json_timetable = []
        for day_idx, day_schedule in enumerate(raw_timetable):
            day_list = []
            for entry in day_schedule:
                day_list.append({
                    "start_time": entry.starttime,
                    "end_time": entry.endtime,
                    "subject": entry.subject,
                    "location": entry.location
                })
            json_timetable.append(day_list)
            
        return jsonify({
            "status": "success",
            "course_section": cosec,
            "timetable": json_timetable
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    print("Starting timetable API server on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
