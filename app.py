import os
import re
import time
import logging
from collections import defaultdict
from flask import Flask, request, jsonify
from flask_cors import CORS
from databaseHandler import fetch_timetable_for_section

# === Logging ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# === App Init ===
app = Flask(__name__, static_folder='frontend', static_url_path='')

# Request size limit: reject bodies > 1 MB
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1 MB

# CORS: only allow API routes, not the entire app
CORS(app, resources={r"/api/*": {"origins": "*"}})

# === Constants ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUBJECTS_DB = os.path.join(BASE_DIR, "subjects.db")
COURSE_DB = os.path.join(BASE_DIR, "uni_timetable.db")
LAB_DB = os.path.join(BASE_DIR, "uni_timetable_lab.db")

# === Input Validation ===
COURSE_PATTERN = re.compile(r'^[A-Za-z0-9]{1,10}$')
SECTION_PATTERN = re.compile(r'^[A-Za-z0-9]{1,5}$')
MAX_SUBJECTS = 20
MAX_SUBJECT_LENGTH = 100

# === Simple In-Memory Rate Limiter (no extra dependency) ===
_rate_store = defaultdict(list)
RATE_LIMIT = 15          # max requests
RATE_WINDOW = 60         # per 60 seconds


def _is_rate_limited(client_ip: str) -> bool:
    """Returns True if the client has exceeded the rate limit."""
    now = time.time()
    timestamps = _rate_store[client_ip]
    # Prune old timestamps
    _rate_store[client_ip] = [t for t in timestamps if now - t < RATE_WINDOW]
    if len(_rate_store[client_ip]) >= RATE_LIMIT:
        return True
    _rate_store[client_ip].append(now)
    return False


# === Security Headers ===
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'
    # Only set CSP on HTML responses (not JSON API responses)
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
    return response


# === Error Handlers ===
@app.errorhandler(400)
def bad_request(e):
    return jsonify({"status": "error", "message": "Bad request"}), 400


@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Not found"}), 404


@app.errorhandler(413)
def payload_too_large(e):
    return jsonify({"status": "error", "message": "Request too large"}), 413


@app.errorhandler(429)
def rate_limit_exceeded(e):
    return jsonify({"status": "error", "message": "Too many requests, please slow down"}), 429


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"status": "error", "message": "Internal server error"}), 500


# === Routes ===
@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/api/batches', methods=['GET'])
def get_batches():
    """Returns a list of all batches and their color codes from subjects.db"""
    import sqlite3
    try:
        with sqlite3.connect(SUBJECTS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, color_hex FROM batches ORDER BY id ASC")
            rows = cursor.fetchall()
            batches = [{"id": row[0], "name": row[1], "color_hex": row[2]} for row in rows]
            return jsonify({"status": "success", "data": batches})
    except Exception as e:
        logger.exception("Failed to fetch batches")
        return jsonify({"status": "error", "message": "Failed to load batches"}), 500


@app.route('/api/subjects', methods=['GET'])
def get_subjects():
    """Returns subjects from subjects.db, optionally filtered by ?batch= parameter."""
    import sqlite3
    batch = request.args.get('batch', '').strip()
    try:
        with sqlite3.connect(SUBJECTS_DB) as conn:
            cursor = conn.cursor()
            if batch:
                cursor.execute("""
                    SELECT s.id, s.name, s.short_name 
                    FROM subjects s
                    JOIN batch_subjects bs ON s.id = bs.subject_id
                    JOIN batches b ON bs.batch_id = b.id
                    WHERE LOWER(b.name) = LOWER(?) OR LOWER(b.name) LIKE LOWER(?)
                    ORDER BY s.name ASC
                """, (batch, f"%{batch}%"))
            else:
                cursor.execute("SELECT id, name, short_name FROM subjects ORDER BY name ASC")
            
            rows = cursor.fetchall()
            subjects = [{"id": row[0], "name": row[1], "short_name": row[2]} for row in rows]
            return jsonify({"status": "success", "data": subjects})
    except Exception as e:
        logger.exception("Failed to fetch subjects")
        return jsonify({"status": "error", "message": "Failed to load subjects"}), 500



@app.route('/api/subjects/repeat', methods=['GET'])
def get_repeat_subjects():
    """Returns repeat subjects excluding subjects already in the user's own batch.
    Query params: ?batch=<batch_name> (the user's primary batch to exclude).
    """
    import sqlite3
    user_batch = request.args.get('batch', '').strip()
    try:
        with sqlite3.connect(SUBJECTS_DB) as conn:
            cursor = conn.cursor()
            if user_batch:
                # Get repeat subjects that are NOT in the user's primary batch
                cursor.execute("""
                    SELECT DISTINCT s.id, s.name, s.short_name
                    FROM subjects s
                    JOIN batch_subjects bs ON s.id = bs.subject_id
                    JOIN batches b ON bs.batch_id = b.id
                    WHERE b.name = 'Repeat Courses'
                    AND s.id NOT IN (
                        SELECT bs2.subject_id FROM batch_subjects bs2
                        JOIN batches b2 ON bs2.batch_id = b2.id
                        WHERE LOWER(b2.name) = LOWER(?)
                    )
                    ORDER BY s.name ASC
                """, (user_batch,))
            else:
                # No batch filter — return all repeat subjects
                cursor.execute("""
                    SELECT DISTINCT s.id, s.name, s.short_name
                    FROM subjects s
                    JOIN batch_subjects bs ON s.id = bs.subject_id
                    JOIN batches b ON bs.batch_id = b.id
                    WHERE b.name = 'Repeat Courses'
                    ORDER BY s.name ASC
                """)

            rows = cursor.fetchall()
            subjects = [{"id": row[0], "name": row[1], "short_name": row[2]} for row in rows]
            return jsonify({"status": "success", "data": subjects})
    except Exception as e:
        logger.exception("Failed to fetch repeat subjects")
        return jsonify({"status": "error", "message": "Failed to load repeat subjects"}), 500


@app.route('/api/subjects/electives', methods=['GET'])
def get_elective_subjects():
    """Returns all available elective course subjects."""
    import sqlite3
    try:
        with sqlite3.connect(SUBJECTS_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT s.id, s.name, s.short_name
                FROM subjects s
                JOIN batch_subjects bs ON s.id = bs.subject_id
                JOIN batches b ON bs.batch_id = b.id
                WHERE b.name = 'Elective Courses'
                ORDER BY s.name ASC
            """)
            rows = cursor.fetchall()
            subjects = [{"id": row[0], "name": row[1], "short_name": row[2]} for row in rows]
            return jsonify({"status": "success", "data": subjects})
    except Exception as e:
        logger.exception("Failed to fetch elective subjects")
        return jsonify({"status": "error", "message": "Failed to load elective subjects"}), 500


MAX_REPEAT_COURSES = 10

@app.route('/api/timetable', methods=['POST'])
def get_timetable():
    """
    Accepts JSON like:
    {
      "course": "CS", "section": "A",
      "subjects": ["OOP", "DLD"],
      "repeat_courses": [
        {"subject": "Linear Algebra", "course": "CS", "section": "B"},
        {"subject": "PF", "course": "SE", "section": "A"}
      ]
    }
    Returns the merged timetable including primary + repeat courses.
    """
    # --- Rate limiting ---
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip:
        client_ip = client_ip.split(',')[0].strip()
    if _is_rate_limited(client_ip):
        logger.warning("Rate limited: %s", client_ip)
        return jsonify({"status": "error", "message": "Too many requests, please slow down"}), 429

    # --- Parse JSON safely ---
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"status": "error", "message": "Invalid or missing JSON body"}), 400

    batch = data.get('batch', '')
    course = data.get('course', '')
    section = data.get('section', '')
    subjects = data.get('subjects', [])
    repeat_courses = data.get('repeat_courses', [])

    # --- Type checks ---
    if not isinstance(course, str) or not isinstance(section, str) or not isinstance(batch, str):
        return jsonify({"status": "error", "message": "Batch, course and section must be strings"}), 400
    if not isinstance(subjects, list):
        return jsonify({"status": "error", "message": "Subjects must be a list"}), 400
    if not isinstance(repeat_courses, list):
        return jsonify({"status": "error", "message": "repeat_courses must be a list"}), 400

    batch = batch.strip()
    course = course.strip().upper()
    section = section.strip().upper()

    # --- Validate format ---
    if not course or not COURSE_PATTERN.match(course):
        return jsonify({"status": "error", "message": "Invalid course format (alphanumeric, 1-10 chars)"}), 400
    if not section or not SECTION_PATTERN.match(section):
        return jsonify({"status": "error", "message": "Invalid section format (alphanumeric, 1-5 chars)"}), 400
    if not subjects and not repeat_courses:
        return jsonify({"status": "error", "message": "At least one subject is required"}), 400
    if len(subjects) > MAX_SUBJECTS:
        return jsonify({"status": "error", "message": f"Too many subjects (max {MAX_SUBJECTS})"}), 400
    if len(repeat_courses) > MAX_REPEAT_COURSES:
        return jsonify({"status": "error", "message": f"Too many repeat courses (max {MAX_REPEAT_COURSES})"}), 400

    # --- Validate each primary subject ---
    sanitized_subjects = []
    for sub in subjects:
        if not isinstance(sub, str):
            return jsonify({"status": "error", "message": "Each subject must be a string"}), 400
        sub = sub.strip()
        if not sub or len(sub) > MAX_SUBJECT_LENGTH:
            return jsonify({"status": "error", "message": f"Subject names must be 1-{MAX_SUBJECT_LENGTH} characters"}), 400
        sanitized_subjects.append(sub)

    # --- Validate each repeat course entry ---
    sanitized_repeats = []
    for rc in repeat_courses:
        if not isinstance(rc, dict):
            return jsonify({"status": "error", "message": "Each repeat_course must be an object"}), 400
        rc_subject = rc.get('subject', '')
        rc_course = rc.get('course', '')
        rc_section = rc.get('section', '')
        if not isinstance(rc_subject, str) or not isinstance(rc_course, str) or not isinstance(rc_section, str):
            return jsonify({"status": "error", "message": "Repeat course fields must be strings"}), 400
        rc_subject = rc_subject.strip()
        rc_course = rc_course.strip().upper()
        rc_section = rc_section.strip().upper()
        if not rc_subject or not rc_course or not rc_section:
            return jsonify({"status": "error", "message": "Repeat course subject, course and section are all required"}), 400
        if not COURSE_PATTERN.match(rc_course):
            return jsonify({"status": "error", "message": f"Invalid repeat course format: {rc_course}"}), 400
        if not SECTION_PATTERN.match(rc_section):
            return jsonify({"status": "error", "message": f"Invalid repeat section format: {rc_section}"}), 400
        sanitized_repeats.append({
            'subject': rc_subject,
            'cosec': f"{rc_course}-{rc_section}"
        })

    cosec = f"{course}-{section}"

    def parse_time(time_str):
        try:
            h, m = map(int, time_str.split(':'))
            if 1 <= h <= 7:
                h += 12
            return h * 60 + m
        except Exception:
            return 0

    try:
        # --- Fetch primary section timetable ---
        raw_timetable = [[] for _ in range(5)]

        if sanitized_subjects:
            primary_course = fetch_timetable_for_section(COURSE_DB, cosec, sanitized_subjects, batch)
            primary_lab = fetch_timetable_for_section(LAB_DB, cosec, sanitized_subjects, batch)
            for i in range(5):
                raw_timetable[i].extend(primary_course[i])
                raw_timetable[i].extend(primary_lab[i])

        # --- Fetch repeat courses (each with its own section) ---
        for rc in sanitized_repeats:
            rc_course_entries = fetch_timetable_for_section(COURSE_DB, rc['cosec'], [rc['subject']])
            rc_lab_entries = fetch_timetable_for_section(LAB_DB, rc['cosec'], [rc['subject']])
            for i in range(5):
                raw_timetable[i].extend(rc_course_entries[i])
                raw_timetable[i].extend(rc_lab_entries[i])

        # --- Sort each day by start time ---
        for i in range(5):
            raw_timetable[i].sort(key=lambda r: parse_time(r.starttime))

        # Convert objects to dicts for JSON serialization
        json_timetable = []
        for day_schedule in raw_timetable:
            day_list = []
            for entry in day_schedule:
                day_list.append({
                    "start_time": entry.starttime,
                    "end_time": entry.endtime,
                    "subject": entry.subject,
                    "location": entry.location
                })
            json_timetable.append(day_list)

        total_classes = sum(len(d) for d in json_timetable)
        logger.info("Timetable generated for %s + %d repeats (%d classes)",
                    cosec, len(sanitized_repeats), total_classes)

        return jsonify({
            "status": "success",
            "course_section": cosec,
            "timetable": json_timetable
        })
    except Exception as e:
        logger.exception("Failed to generate timetable for %s", cosec)
        return jsonify({"status": "error", "message": "Failed to generate timetable"}), 500


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    port = int(os.environ.get('PORT', 5000))
    
    if debug_mode:
        logger.info("Starting timetable API server in DEV mode on http://127.0.0.1:%d", port)
        app.run(debug=True, port=port)
    else:
        logger.info("Starting timetable API server in PRODUCTION WSGI mode on port %d", port)
        try:
            from waitress import serve
            serve(app, host='0.0.0.0', port=port)
        except ImportError:
            logger.warning("waitress not installed. Falling back to Flask dev server.")
            app.run(debug=False, port=port)
