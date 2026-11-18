# AI Agent Engineering Task: Timetable Maker Fixes & Ingestion Specification

> **Target Repository:** `TimeTable_Maker`  
> **Author / Upstream Consumer:** `FAST_Faculty_TimeTable`  
> **Date:** November 2026  
> **Scope:** Fix faculty assignment collisions, missing electives, tutorial classification, malformed timeslots, and SQL wildcard leaks in `databaseHandler.py` and `sync_faculty_to_supabase.py`.

---

## 1. Executive Summary & Context

`TimeTable_Maker` is the upstream data pipeline responsible for:
1. Parsing Google Sheets timetable grids into local SQLite databases (`uni_timetable.db` and `uni_timetable_lab.db`) via `databaseHandler.py`.
2. Ingesting the official faculty course allocation workbook (`Course Allocation - Fall-2026, School of Computing.xlsx`) via `sync_faculty_to_supabase.py`.
3. Pre-compiling weekly faculty schedules and upserting them into the Supabase PostgreSQL table `public.faculty_schedules`.

A comprehensive cross-repository audit between `FAST_Faculty_TimeTable` and `TimeTable_Maker` identified **6 critical pipeline defects** in `TimeTable_Maker` that directly cause timetable collisions, missing electives, corrupted timeslots, and unclassified tutorial classes in the downstream consumer application.

---

## 2. Issues & Exact Implementation Instructions

### Issue 1: Ms. Noor Ul Ain Duplicate Name Collision & Disambiguation
* **Target File:** `sync_faculty_to_supabase.py`
* **Affected Function:** `find_faculty_match()` (lines 401–480) and `compile_faculty_schedules()` (lines 730–760)

#### Root Cause
In `frontend/data/faculty.bin` and the university faculty roster, there are **two distinct individuals** with the identical name:
1. `Ms. Noor ul Ain` — **Assistant Professor**, Department of **Computer Science** (`noorul.ain@nu.edu.pk`)
2. `Ms. Noor ul Ain` — **Instructor**, Department of **Software Engineering** (`noor.ulain@isb.nu.edu.pk`)

In `find_faculty_match()`, the name matching loop returns the first record where `clean_target == clean_fac`. As a result, the CS Assistant Professor received both her CS Theory classes (*Computer Architecture*, sections `BCS-5C/D/F`) **and** the SE Instructor's Lab classes (*Artificial Intelligence Lab*, sections `BSE-5A/B/C`). The SE Instructor received 0 classes, creating major timetable clashes for the CS professor on Mondays.

#### Implementation Instructions
Update `find_faculty_match` to accept context parameters (`department`, `discipline`, `is_lab`, `course_title`):
```python
def find_faculty_match(
    teacher_name: str, 
    faculty_roster: List[Dict[str, Any]], 
    threshold: float = 0.92,
    discipline: str = "",
    is_lab: bool = False,
    department: str = "",
    course_title: str = ""
) -> Optional[Dict[str, Any]]:
```
When multiple candidate records match the cleaned name (e.g. `len(candidates) > 1`):
1. **Discipline / Department Match:**
   - If `discipline == "SE"` or `"(se)"` in `course_title.lower()`: Prefer the candidate with `"software"` in their `dept.lower()`.
   - If `discipline == "CS"` or `"(cs)"` in `course_title.lower()`: Prefer the candidate with `"computer"` in their `dept.lower()`.
2. **Designation / Lab Match:**
   - If `is_lab is True`: Prefer candidates with `desig == "Instructor"`.
   - If `is_lab is False`: Prefer candidates with `desig in {"Assistant Professor", "Associate Professor", "Professor", "Lecturer"}`.

In `compile_faculty_schedules()`, pass these fields from the `alloc` dictionary into `find_faculty_match()`:
```python
disc = alloc.get("timetable_section", "").split("-")[0] if "-" in alloc.get("timetable_section", "") else ""
match = find_faculty_match(
    instr_name,
    faculty_roster,
    threshold=0.92,
    discipline=disc,
    is_lab=alloc.get("is_lab", False),
    department=alloc.get("sheet", ""),
    course_title=alloc.get("course_title", "")
)
```

---

### Issue 2: Senior Open-Pool Electives Dropped in Continuous Sync
* **Target File:** `sync_faculty_to_supabase.py`
* **Affected Function:** `sync_from_existing_database()` (lines 1215–1255)

#### Root Cause
In `uni_timetable.db`, senior open-pool undergraduate electives (e.g. `Fund of SPM` taught by Dr. Hina Ayaz, `SMD` taught by Mr. Muhammad Saad Salman, `Deep Learn` taught by Dr. Ahmad Raza Shahid) have an **empty section** (`SECTION = ''`) because the course is open to the entire batch (`BS 23 CS`):
```sql
(175, 'Monday', '11:30', '12:50', 'Fund of SPM', 'D-404', '', 'BS 23 CS', NULL)
(178, 'Monday', '11:30', '12:50', 'SMD', 'D-405', '', 'BS 23 CS', NULL)
```
While `compile_faculty_schedules()` has a query for blank sections, `sync_from_existing_database()` (the continuous sync function) was missing this query completely. Running `python sync_faculty_to_supabase.py --continuous` drops these electives from faculty profiles.

#### Implementation Instructions
In `sync_from_existing_database()`, inside `for target_cursor, location_col, actual_lab in cursors_to_try:` (around lines 1220–1240), add the missing query to `queries_to_try`:
```python
# Exact batch with blank/null section (open pool senior electives e.g. Fund of SPM, SMD, Deep Learn)
queries_to_try.append({
    "query": f"{select_clause} WHERE BATCH = ? AND (SECTION = '' OR SECTION IS NULL) AND {subj_cond}",
    "params": (b_name,) + subj_params
})
```
Also add the global section-agnostic blank-section query around line 1259:
```python
# Final Fallback (Ignore batch completely with blank/null section)
queries_to_try.append({
    "query": f"{select_clause} WHERE (SECTION = '' OR SECTION IS NULL) AND {subj_cond}",
    "params": subj_params
})
```

---

### Issue 3: Subject Acronym & Canonical Name Mismatches
* **Target File:** `sync_faculty_to_supabase.py`
* **Affected Dictionary:** `CANONICAL_SUBJECT_MAP` (lines 150–320)

#### Root Cause & Required Fixes
1. **Fundamentals of Data Visualization (`CS3012`):**
   - **Current:** `"fundamentals of data visualization": "Data Visualization"`
   - **Database Value:** In `uni_timetable.db`, the subject is `'Fund of Data Vis'`.
   - **Fix:** Update to:
     ```python
     "fundamentals of data visualization": "Fund of Data Vis",
     ```
     *(Fixes missing 3rd course for Dr. Faisal Cheema).*
2. **Security Operations and Administration (`CY4048`):**
   - **Current:** Missing theory mapping (only had lab mapping).
   - **Database Value:** In `uni_timetable.db`, stored as `'Security Ops'`.
   - **Fix:** Add:
     ```python
     "security operations and administration": "Security Ops",
     ```
     *(Fixes missing course for Dr. Zafar Iqbal).*
3. **Typo in Programming for AI Lab (`AL2001`):**
   - **Current (line 304):** `"programming for ai lab": "Prof for AI Lab"` (typo: `"Prof"` instead of `"Prog"`).
   - **Database Value:** In `uni_timetable_lab.db`, stored as `'Prog for AI Lab'`.
   - **Fix:** Change to:
     ```python
     "programming for ai lab": "Prog for AI Lab",
     ```
     *(Restores slots for Mr. Ali Hamza, who currently has 0 slots).*
4. **Holy Quran Course Suffixes (`SS1022`):**
   - In `uni_timetable.db`, 2nd-year Quran is often scheduled as `'UHQ-I&II'`.
   - **Fix:** Ensure canonical resolution for `understanding of holy quran-ii` also queries `'UHQ-I&II'`.

---

### Issue 4: Wildcard SQL Collisions on Short Acronyms
* **Target File:** `sync_faculty_to_supabase.py`
* **Affected Lines:** line 837 in `compile_faculty_schedules()` and line 1210 in `sync_from_existing_database()`

#### Root Cause
The current condition is:
```python
subj_cond = "(SUBJECT = ? OR SUBJECT LIKE ? OR SUBJECT = ? OR SUBJECT LIKE ?)"
subj_params = (canonical_subj, f"%{canonical_subj}%", base_subj, f"%{base_subj}%")
```
SQLite's `LIKE` is case-insensitive ASCII. When `canonical_subj` is short (e.g. `LA` for Linear Algebra), `SUBJECT LIKE '%LA%'` matches **any subject containing the letters "la"**, such as:
- `'Data St Lab'` (matches `%LA%` because of `Lab`)
- `'Func Eng Lab'`
- `'OOP Lab'`

This falsely assigned Friday `Data St Lab [CS-B]` slots to Dr. Nabila Ahmad (who only teaches Linear Algebra `LA`), producing artificial schedule clashes. Similarly, theory teachers for Programming Fundamentals (`PF`) matched classroom reschedules of `'PF Lab'`.

#### Implementation Instructions
Guard short acronyms ($\le 3$ characters, e.g. `LA`, `PF`, `AI`, `DB`, `AP`, `OS`, `ML`):
```python
if len(canonical_subj) <= 3:
    # Strict equality for short acronyms to prevent '%LA%' matching 'Data St Lab'
    subj_cond = "(SUBJECT = ? OR SUBJECT = ?)"
    subj_params = (canonical_subj, base_subj)
else:
    subj_cond = "(SUBJECT = ? OR SUBJECT LIKE ? OR SUBJECT = ? OR SUBJECT LIKE ?)"
    subj_params = (canonical_subj, f"%{canonical_subj}%", base_subj, f"%{base_subj}%")
```

---

### Issue 5: Tutorial Keywords Stripped into `NULL` Status
* **Target File:** `databaseHandler.py`
* **Affected Functions:** `STATUS_PATTERN` (lines 143–146) and `extract_status()` (lines 148–174)

#### Root Cause
Google Sheets contains 15 active tutorial sessions, formatted as:
`PF (CS-C) Tutorial [BS 26 CS]` (Room `D-401`, Thursday 01:00–02:20)
`PF (CS-G) Tutorial [BS 26 CS]` (Room `D-404`, Thursday 02:30–03:50)

Because `STATUS_PATTERN` did not include `Tutorial|Tut`, `separate_subject_and_section()` split by `(` and discarded `" Tutorial"`. The database saved `STATUS = NULL`, making tutorials indistinguishable from regular lectures.

#### Implementation Instructions
1. Update `STATUS_PATTERN` in `databaseHandler.py`:
```python
STATUS_PATTERN = re.compile(
    r'[\s\-_\(\[]*\b(Cancell?ed|Cancel|Resch(?:edul(?:ed|e)|udl(?:ed|e)|ed|uled)?|Re-?sch(?:edul(?:ed|e))?|Reserved?|Postponed?|Tutorial|Tut)\b[\s\-_\)\]]*',
    re.IGNORECASE
)
```
2. In `extract_status()`, add the tutorial branch:
```python
elif raw.startswith('tut'):
    status = 'Tutorial'
```
*(Downstream consumer `FAST_Faculty_TimeTable` already has `<div class="card-status status-${cls.status}">` and will render a dedicated purple badge once this status is stored).*

---

### Issue 6: Malformed Time Slot Splitting
* **Target File:** `databaseHandler.py`
* **Affected Function:** `separate_time_slot()` (lines 290–300)

#### Root Cause
When classroom annotations leak into time column headers (e.g. `02:30 (C-305)`), the fallback code `parts = time_slot.split('-')` produced:
`START_TIME = '02:30 (C'`, `END_TIME = '305)'` (saved as row 229 in `uni_timetable.db`).

#### Implementation Instructions
In `separate_time_slot()`, enforce strict regex validation. If a clean `HH:MM - HH:MM` interval is not found, do not perform arbitrary hyphen splitting:
```python
def separate_time_slot(time_slot: str) -> tuple:
    match = re.search(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})', time_slot)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    
    # If no valid time range is matched, do not return malformed strings like ('02:30 (C', '305)')
    return "", ""
```

---

## 3. Verification & Acceptance Criteria

After making the code edits in `TimeTable_Maker`:

1. **Rebuild the Timetable Database:**
   ```bash
   cd TimeTable_Maker
   source .venv/bin/activate
   python rebuild_db.py
   ```
   *Verify that all 15 tutorial cells in `uni_timetable.db` now have `STATUS = 'Tutorial'`.*

2. **Run Schedule Compilation Dry Run:**
   ```bash
   python sync_faculty_to_supabase.py --dry-run
   ```
   Verify:
   - Ms. Noor ul Ain (`noorul.ain@nu.edu.pk`) has **6 theory slots** (*Comp Arch* only).
   - Ms. Noor ul Ain (`noor.ulain@isb.nu.edu.pk`) has **3 lab slots** (*AI Lab* only).
   - Dr. Hina Ayaz has `Fund of SPM` included (total slots = 6).
   - Mr. Muhammad Saad Salman has `SMD` included (total slots = 6).
   - Dr. Faisal Cheema has `Fund of Data Vis` included (all 3 courses present, total slots = 7).
   - Mr. Ali Hamza has `Prog for AI Lab` matched (slots > 0).
   - Dr. Nabila Ahmad has NO Friday clash with `Data St Lab`.
   - Total faculty with 0 slots drops to 0 (excluding non-teaching thesis/FYP supervisors).

3. **Deploy to Supabase:**
   ```bash
   python sync_faculty_to_supabase.py --semester 2026-fall
   ```

4. **Notify Downstream UI (`FAST_Faculty_TimeTable`):**
   Once synced to Supabase, update `FAST_Faculty_TimeTable/public/style.css` with `.status-tutorial` and re-export `data/active_faculty_summary.json`.
