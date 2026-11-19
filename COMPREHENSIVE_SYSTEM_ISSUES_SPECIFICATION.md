# Master System Audit & Comprehensive Issue Specification
**Project:** Fast NUCES Islamabad Timetable Ecosystem (`TimeTable_Maker` & `FAST_Faculty_TimeTable`)  
**Generated Date:** 2026-11-19  
**Target Audience:** Autonomous Engineering Agents, System Architects, QA Reviewers  

---

## 1. Executive Summary & Architectural Overview

The FAST NUCES Islamabad Timetable system consists of two distinct repositories serving two distinct user personas:
1. **`TimeTable_Maker` (Student Timetable Engine):**
   * Responsible for ingesting timetable schedules from Google Sheets (Monday through Saturday).
   * Parses timeslots, classrooms, lab assignments, section codes, batches, and status flags.
   * Stores data in two SQLite databases:
     * `uni_timetable.db` (Theory classrooms)
     * `uni_timetable_lab.db` (Computer & Hardware labs)
   * Serves student section lookup (`fetch_timetable_for_section`) and timetable generation.
2. **`FAST_Faculty_TimeTable` (Faculty Timetable & Availability Engine):**
   * Ingests academic course allocations from `Course Allocation - Fall-2026, School of Computing.xlsx`.
   * Joins instructor assignments with the parsed SQLite timetable databases via `sync_faculty_to_supabase.py`.
   * Publishes compiled weekly faculty schedules, office hour free-slots, and clash detection to Supabase PostgreSQL and downstream JSON feeds.

This document compiles **every single known defect, structural edge case, and architectural divergence** discovered across the pipeline. It provides complete timings, locations, instructors, root cause traces, and explicit implementation blueprints for worker subagents.

---

## 2. Master Issue Inventory

```
+----+---------------------------------------------------------------+-----------------------------------+--------------------+
| ID | Issue Title                                                   | Primary System Component          | Impacted Persona   |
+----+---------------------------------------------------------------+-----------------------------------+--------------------+
| 01 | Ms. Noor Ul Ain Identity & Discipline Collision              | sync_faculty_to_supabase.py       | Faculty App        |
| 02 | Senior Electives Dropped in Continuous Sync (SECTION = '')     | sync_faculty_to_supabase.py       | Faculty App        |
| 03 | Canonical Subject Shorthand Mismatches & Dictionary Typos     | sync_faculty_to_supabase.py       | Faculty App        |
| 04 | Short Acronym Wildcard Collisions (e.g. 'LA' vs 'Data St Lab')| sync_faculty_to_supabase.py       | Faculty App        |
| 05 | Tutorial Classes Stripped to NULL by STATUS_PATTERN           | databaseHandler.py                | Student & Faculty  |
| 06 | Malformed Timeslot Regex Splits on Parenthetical Room Decoys  | databaseHandler.py                | Student & Faculty  |
| 07 | Decoy / Pointer Rooms Creating Phantom Duplicate Clashes      | databaseHandler.py / sync script  | Student & Faculty  |
| 08 | Persona Divergence for Cancelled Classes                      | Dual Pipeline Architecture        | Student vs Faculty |
| 09 | Combined / Slashed Sections Ingestion & Student Erasure       | databaseHandler.py & sync script  | Student & Faculty  |
| 10 | Cross-Database Fallback Stealing Other Teachers' Theory Slot  | sync_faculty_to_supabase.py       | Faculty App        |
+----+---------------------------------------------------------------+-----------------------------------+--------------------+
```

---

## 3. Deep-Dive Issue Specifications

---

### Issue 01: Ms. Noor Ul Ain Identity & Discipline Collision

#### Context & Exact Data
* **Faculty Directory:** Contains two distinct faculty members named **Noor Ul Ain**:
  1. `noorulain.khattak@isb.nu.edu.pk` — Assistant Professor, Department of Computer Science (CS). Teaches Theory courses.
  2. `noor.ulain@isb.nu.edu.pk` — Lecturer / Lab Instructor, Department of Software Engineering (SE).
* **Allocation Sheet Rows:**
  * `Computing-Labs` Rows 134–136:
    * `AL2002` — Artificial Intelligence Lab (SE)
    * Sections: `BSE-5A`, `BSE-5B`, `BSE-5C` (50, 48, 45 students)
    * Instructor: `Ms. Noor Ul Ain` (Software Engineering lab instructor)

#### What Happens & Why It Fails
In `find_faculty_match()` inside `sync_faculty_to_supabase.py`:
* The name normalization resolves both to `"noor ul ain"`.
* The candidate search finds 2 matches.
* When the function attempts to disambiguate:
  * Without checking the section discipline prefix (`BSE` vs `BCS`) or role (`is_lab`), the system picks the first match in alphabetical or database order (`noorulain.khattak@isb.nu.edu.pk`).
  * As a result, the CS Assistant Professor is falsely assigned Software Engineering AI labs (`BSE-5A/B/C`), while the SE Lecturer's schedule remains completely empty.

#### Required Agent Action
In `find_faculty_match()`:
* Inspect `discipline` (`BSE` vs `BCS`/`BAI`), `is_lab`, and course title.
* If `discipline == 'BSE'` or `is_lab=True` for SE labs, match candidate with email `noor.ulain@isb.nu.edu.pk`.
* If CS theory, match candidate `noorulain.khattak@isb.nu.edu.pk`.

---

### Issue 02: Senior Electives Dropped in Continuous Sync (`SECTION = ''`)

#### Context & Exact Data
* **Courses:** Senior open-pool undergraduate electives:
  * `Fund of SPM` (Fundamentals of Software Project Management)
  * `SMD` (Software Modeling & Design)
  * `Agentic AI`
* **Timetable Database State:**
  * These classes are shared across multiple disciplines and sections.
  * In `uni_timetable.db`, they are stored with `SECTION = ''` or `SECTION IS NULL` and `BATCH = 'BS 23 CS'` (or `BS 23 AI`, etc.).

#### What Happens & Why It Fails
* During the continuous sync function `sync_from_existing_database()`:
  * Queries looking for allocations only checked `WHERE SECTION = ?` or `SECTION LIKE ?`.
  * Because `SECTION` is empty string (`''`), these queries return 0 rows.
  * Dr. Zafar Iqbal, Dr. Faisal Cheema, and other senior elective professors lose their elective lectures during continuous sync.

#### Required Agent Action
In `sync_from_existing_database()`, include open-pool elective queries:
```sql
SELECT ... FROM timetable WHERE BATCH = ? AND (SECTION = '' OR SECTION IS NULL) AND (SUBJECT = ? OR SUBJECT LIKE ?)
```

---

### Issue 03: Canonical Subject Shorthand Mismatches & Dictionary Typos

#### Context & Exact Data
The Course Allocation Excel workbook contains full descriptive titles, whereas Google Sheets contains compact abbreviations.
Several dictionary keys in `CANONICAL_SUBJECT_MAP` failed to resolve:

1. **Typo in Programming for AI Lab:**
   * Allocation Title: `Programming for AI Lab`
   * Map had: `"programing for ai lab": "Prog for AI Lab"` (missing second 'm' in programming).
   * Affected Faculty: **Mr. Ali Hamza** — his lab was completely omitted.
2. **Shorthand Mismatch in Data Visualization:**
   * Allocation Title: `Fundamentals of Data Visualization`
   * Google Sheet Subject: `Fund of Data Vis`
   * Map resolved to: `Data Vis` (did not match `Fund of Data Vis` in timetable).
   * Affected Faculty: **Dr. Faisal Cheema** — his 3rd course failed to match.
3. **Missing Cyber Security Elective Mapping:**
   * Allocation Title: `Security Operations and Administration`
   * Google Sheet Subject: `Security Ops` or `Sec Ops`
   * Affected Faculty: **Dr. Zafar Iqbal** — Cyber elective missing.
4. **Quran Course Combined Syntax (`UHQ-II` vs `UHQ-I&II`):**
   * Allocation lists: `Understanding of Holy Quran-II (CS)` -> `UHQ-II`.
   * Timetable cells contain: `UHQ-I&II (CS-F) 09:30-11:20` (combined course code).
   * Query for `UHQ-II` failed to match `UHQ-I&II`.

#### Required Agent Action
Update `CANONICAL_SUBJECT_MAP` with exact lowercase variants:
* `"programming for ai lab": "Prog for AI Lab"`
* `"fundamentals of data visualization": "Fund of Data Vis"`
* `"security operations and administration": "Security Ops"`
In `compile_faculty_schedules()`, when `canonical_subj in ("UHQ-II", "UHQ-I&II")`, query both variants.

---

### Issue 04: Short Acronym Wildcard Collisions (`LA` vs `Data St Lab`)

#### Context & Exact Data
* **Course:** `LA` (Linear Algebra, Theory).
* Query template in `compile_faculty_schedules()`:
  ```python
  subj_cond = "(SUBJECT = ? OR SUBJECT LIKE ? OR SUBJECT = ? OR SUBJECT LIKE ?)"
  subj_params = (canonical_subj, f"%{canonical_subj}%", base_subj, f"%{base_subj}%")
  ```
* When `canonical_subj = 'LA'`:
  * `SUBJECT LIKE '%LA%'` matches:
    * `LA` (Linear Algebra)
    * `Data St Lab` (contains `La` in `Lab`!)
    * `PF Lab`
    * `DLD Lab`

#### What Happens & Why It Fails
Faculty members teaching Linear Algebra were assigned other instructors' computer labs because SQL `LIKE '%LA%'` matches the substring `"Lab"`.

#### Required Agent Action
Enforce strict equality for short acronyms:
```python
if len(canonical_subj) <= 3:
    subj_cond = "(SUBJECT = ? OR SUBJECT = ?)"
    subj_params = (canonical_subj, base_subj)
```

---

### Issue 05: Tutorial Classes Stripped to NULL by `STATUS_PATTERN`

#### Context & Exact Data
* **Google Sheet Cells:**
  * Wednesday `C-406` (02:30–03:50): `PF (CS-A&B) Tutorial`
  * Wednesday `C-302` (11:30–12:50): `PF (SE-D) Tutorial/ Reserved`
  * Total 15 tutorial cells exist in the timetable sheet.

#### What Happens & Why It Fails
In `databaseHandler.py`:
```python
STATUS_PATTERN = re.compile(r'\b(ReSch|Cancelled|Cancel)\b', re.IGNORECASE)
```
* `extract_status()` only recognized `ReSch` and `Cancelled`.
* The word `Tutorial` was left unparsed or stripped into `STATUS = NULL`, and in some regex passes leaked into the section string.

#### Required Agent Action
Update regex in `databaseHandler.py`:
```python
STATUS_PATTERN = re.compile(r'\b(ReSch|Cancelled|Cancel|Tutorial|Tut)\b', re.IGNORECASE)
```
Ensure `Tutorial` is stored in the `STATUS` column of SQLite and rendered with a `.status-tutorial` badge in frontend UIs.

---

### Issue 06: Malformed Timeslot Regex Splits on Parenthetical Room Decoys

#### Context & Exact Data
* **Google Sheet Cells:**
  * Thursday `C-310` (02:30–04:20): `UHQ-I&II (CS-B) 02:30-04:20 C-311`
  * Thursday `C-601` (01:00–02:45): `Arts & Humanities (SE-C) 01:00-02:45 (D-506)`
  * Monday `C-305`: `02:30 (C-305)`

#### What Happens & Why It Fails
In `separate_time_slot()`:
* The regex split on loose hyphens or colons:
  `times = re.split(r'[-–]', slot_str)`
* For a cell like `02:30 (C-305)`, it split into:
  * Start: `02:30 (C`
  * End: `305)`
* This caused corrupt timestamps in SQLite (`START_TIME = '02:30 (C'`, `END_TIME = '305)'`), crashing chronological sorters.

#### Required Agent Action
Enforce strict military/standard time regex in `separate_time_slot()`:
```python
time_pattern = re.compile(r'(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})')
```
Extract exact digits and isolate room annotations into an alternate location field.

---

### Issue 07: Decoy / Pointer Rooms Creating Phantom Duplicate Clashes

#### Real-World Context (from Timetable Manager)
When a class normally scheduled in Room $A$ (e.g. `C-110`) is shifted to Room $B$ (e.g. `C-301`):
* Students and faculty routinely walk to Room $A$ out of habit.
* To prevent confusion, the timetable manager places a **decoy/pointer** in Room $A$'s cell:
  `Fundamentals of Data Visualization C301`
* Meanwhile, the actual class is held in Room $B$ (`C-301`):
  `Fundamentals of Data Visualization`

#### What Happens & Why It Fails
The ingestion pipeline currently treats **both cells as active classes**:
1. It creates an active slot in `C-110`.
2. It creates an active slot in `C-301`.
* **Result:** Dr. Faisal Cheema's faculty profile shows two simultaneous classes at the exact same hour, triggering a false-positive critical clash warning.

#### Required Agent Action
* **Decoy Detection Logic:**
  * If cell text in Room $A$ contains an explicit pointer to Room $B$ (e.g. matches `\b([A-Z]-\d{3}|C\d{3}|D\d{3})\b` differing from the row header), verify if Room $B$ contains the identical course at the identical time slot.
  * If true, mark Room $A$'s cell as `IS_DECOY = True` or pointer note; do **not** generate a second active lecture slot for clash calculation.

---

### Issue 08: Persona Divergence for Cancelled Classes (Students vs Faculty)

#### Context & Ideology
A single database state cannot be treated identically by student and faculty applications:

| Persona | Objective | Expected System Behavior on "Cancelled" Class |
|---|---|---|
| **Student (`TimeTable_Maker`)** | Wants to know if they need to travel to campus. | **MUST SHOW** the class card with a prominent red `Cancelled` badge. |
| **Faculty (`FAST_Faculty_TimeTable`)** | Wants to know when professors are free for meetings / office hours. | **MUST NOT BLOCK** the time slot. The cancelled lecture must free up the slot so other teachers/students can schedule meetings. It must **not** trigger clash warnings. |

#### Architectural Requirement
* **`TimeTable_Maker` (Student App):**
  * Preserves `STATUS = 'Cancelled'`.
  * Renders the card in the student timetable grid with `.status-cancelled` styling.
* **`FAST_Faculty_TimeTable` (Faculty App):**
  * In `sync_faculty_to_supabase.py`:
    * When computing `weekly_schedule`, mark the slot with `is_cancelled: true`.
    * In free-slot calculation engine (`calculate_free_slots()`), treat `is_cancelled: true` slots as **available free time**, not busy time.
    * Do not evaluate cancelled slots in clash detection matrix.

---

### Issue 09: Combined / Slashed Sections Ingestion & Student Erasure

#### Context & Exact Data
The Google Sheets timetable contains 10 rows where multiple sections or disciplines are compressed into a single cell:

```
THEORY DATABASE (uni_timetable.db):
1. Friday 08:30-09:50 | OOP | AI/DS-A | C-305 | BS Repeat Courses
2. Monday 10:00-11:20 | OOP | AI/DS-A | D-304 | BS Repeat Courses
3. Tuesday 01:00-02:20 | Digital Sustain | CS/CY-A | D-404 | BS Repeat Courses
4. Tuesday 03:55-05:15 | Digital Sustain | CS/CY-B | D-404 | BS Repeat Courses
5. Thursday 01:00-02:20 | Digital Sustain | CS/CY-A | D-404 | BS Repeat Courses
6. Thursday 03:55-05:15 | Digital Sustain | CS/CY-B | D-404 | BS Repeat Courses
7. Thursday 10:00-11:20 | PPIT | CS-B&D | D-411 | BS 23 CS
8. Wednesday 02:30-03:50 | PF | CS-A&B | C-406 | BS 26 CS (Tutorial)

LAB DATABASE (uni_timetable_lab.db):
9. Friday 02:30-05:15 | COAL Lab | AI/DS/CS | Margala 4 (C-212) | BS Repeat Courses
10. Friday 10:00-12:45 | OOP Lab | AI/DS-A | C-Rawal 4 (C-512) | BS Repeat Courses
```

#### What Happens & Why It Fails
1. **Impact on Students (`fetch_timetable_for_section`):**
   * Student timetable lookup runs:
     ```python
     query = "SELECT * FROM timetable WHERE DAY = ? AND SECTION = ? AND SUBJECT IN (...) AND BATCH = ?"
     cursor.execute(query, [day, section, ...])
     ```
   * Because it checks strict equality (`SECTION = 'AI-A'`), it **fails to match** `'AI/DS-A'`, `'CS/CY-A'`, `'CS-A&B'`, or `'AI/DS/CS'`.
   * **Result:** Students enrolled in `AI-A`, `DS-A`, `CS-A`, `CY-A`, `CS-B`, and `CS-D` have these classes completely disappear from their generated timetables.
2. **Impact on Faculty (Mr. Usama Bin Imran Example):**
   * In `Course Allocation - Fall-2026, School of Computing.xlsx`, `Computing-Labs` tab:
     * Row 138: `BCS-5A` -> `Mr. Usama Bin Imran`
     * Row 139: `BCS-5B` -> `Mr. Usama Bin Imran`
     * Row 140: `BAI-5A` -> `Mr. Usama Bin Imran`
   * In the Google Sheet timetable: Friday 02:30–05:15 Margala 4 is labeled:
     `COAL Lab (AI/DS/CS, 24)`
   * The timetable ingestion stored `SECTION = 'AI/DS/CS'`.
   * When `sync_faculty_to_supabase.py` compiled Mr. Usama's schedule:
     * It matched the cell because `'AI/DS/CS'` contained substring `'AI'` and `'A'`.
     * BUT it wrote:
       ```python
       "section": row["SECTION"] or sec_name
       ```
     * Result: Instead of showing Mr. Usama's allocated section `BAI-5A` (or `AI-A`), his timetable badge displayed the raw unparsed string **`AI/DS/CS`**.

#### Required Agent Action
1. **Student Ingestion Pipeline (`databaseHandler.py`):**
   * **Row Explosion during SQLite Insertion:** When a cell contains a combined section pattern:
     * `AI/DS-A` -> Explode into two rows: `SECTION = 'AI-A'` and `SECTION = 'DS-A'`
     * `CS/CY-A` -> Explode into two rows: `SECTION = 'CS-A'` and `SECTION = 'CY-A'`
     * `CS-A&B` -> Explode into two rows: `SECTION = 'CS-A'` and `SECTION = 'CS-B'`
     * `AI/DS/CS` -> Explode into three rows: `SECTION = 'AI-A'`, `SECTION = 'DS-A'`, `SECTION = 'CS-A'` (or repeater equivalents)
   * **Benefit:** When a student queries `WHERE SECTION = 'AI-A'`, SQLite returns the record immediately with zero breaking changes to student query APIs.
2. **Faculty Sync Pipeline (`sync_faculty_to_supabase.py`):**
   * When matching an allocation (e.g. `BAI-5A`), assign the slot's section badge as the **allocated section** (`BAI-5A` / `AI-A`) rather than inheriting the raw slashed string from the sheet.

---

### Issue 10: Cross-Database Fallback Stealing Other Teachers' Theory Slots

#### Context & Exact Data
* **Instructor:** **Mr. Usama Bin Imran**
* **Allocation:** `EL2003` — Computer Organization and Assembly Language Lab (CS), Section `BCS-5B` (Lab only, 1 Credit Hour).
* **Theory Instructor:** **Mr. Aqib Rehman** is allocated the Theory course `EE2003` — Computer Organization and Assembly Language (CS) for `BCS-5B`.

#### What Happens & Why It Fails
In `compile_faculty_schedules()` inside `sync_faculty_to_supabase.py`:
* The cursors are ordered with a fallback:
  ```python
  cursors_to_try = [
      (cur_lab, "LAB", True),
      (cur_theory, "CLASSROOM", False)
  ] if is_lab else [
      (cur_theory, "CLASSROOM", False),
      (cur_lab, "LAB", True)
  ]
  ```
* When searching for Mr. Usama's `BCS-5B` lab:
  * `cur_lab` has no explicit `CS-B` slot (repeat lab is scheduled as combined `AI/DS/CS`).
  * The loop fell back to `cur_theory` (the Theory database)!
  * In `cur_theory`, it found `COAL` Section `CS-B` at:
    * Monday 03:55–05:15 in `C-402`
    * Wednesday 03:55–05:15 in `C-403`
  * That slot is **Mr. Aqib Rehman's theory lecture**!
  * **Result:** The script stole Mr. Aqib Rehman's theory lecture and placed it onto Mr. Usama Bin Imran's faculty timetable!

#### Required Agent Action
* **Strict Domain Isolation:**
  * If `is_lab=True`, the search cursor must **STRICTLY QUERY `cur_lab` ONLY**. It must NEVER fall back to `cur_theory`.
  * If `is_lab=False`, the search cursor must **STRICTLY QUERY `cur_theory` ONLY**. It must NEVER fall back to `cur_lab`.
  * If a lab section is combined or unassigned, report it in `unmapped_allocations`, but NEVER steal a theory lecture from another faculty member.

---

## 4. Subagent Work Partitioning Blueprint

When spawning subagents to implement and test these specifications, partition duties as follows:

```
                              +---------------------------------------+
                              |      Master Orchestrator Agent        |
                              +---------------------------------------+
                                        /                   \
                                       /                     \
        +-----------------------------------+     +-----------------------------------+
        |  Subagent A: Student Pipeline     |     |  Subagent B: Faculty Sync         |
        |  Database & Ingestion Architect   |     |  Allocation & Identity Architect  |
        +-----------------------------------+     +-----------------------------------+
        | * databaseHandler.py              |     | * sync_faculty_to_supabase.py     |
        | * Issue 05: Tutorial regex        |     | * Issue 01: Noor Ul Ain matching  |
        | * Issue 06: Timeslot regex split  |     | * Issue 02: Blank section sync    |
        | * Issue 07: Decoy room detection  |     | * Issue 03: Canonical mappings    |
        | * Issue 08: Student cancelled UI  |     | * Issue 04: Acronym len <= 3      |
        | * Issue 09: Section row explosion |     | * Issue 10: Disable cross-DB leak |
        +-----------------------------------+     +-----------------------------------+
```

---

## 5. Acceptance & Verification Matrix

Before any changes are committed or merged, subagents must verify the following tests:

| Test ID | Verification Command / Target | Expected Acceptance Result |
|---|---|---|
| **V-01** | Query `uni_timetable.db` for `SECTION = 'AI-A'` | Returns `OOP` on Mon 10:00 & Fri 08:30 (previously lost under `AI/DS-A`). |
| **V-02** | Query `uni_timetable.db` for `SECTION = 'CS-A'` | Returns `Digital Sustain` and `PF Tutorial` (previously lost under `CS/CY-A` & `CS-A&B`). |
| **V-03** | Query `uni_timetable_lab.db` for `SECTION = 'AI-A'` | Returns `COAL Lab` and `OOP Lab` (previously lost under `AI/DS/CS` & `AI/DS-A`). |
| **V-04** | Verify Ms. Noor Ul Ain faculty profiles | `noor.ulain@isb.nu.edu.pk` has SE AI Labs (`BSE-5A/B/C`). `noorulain.khattak` has CS Theory only. |
| **V-05** | Verify Mr. Usama Bin Imran faculty profile | Does **NOT** have Monday/Wednesday 03:55 PM `COAL CS-B` theory classes. Has proper Friday lab allocations. |
| **V-06** | Verify Mr. Aqib Rehman faculty profile | Retains Monday/Wednesday 03:55 PM `COAL CS-B` theory lectures in `C-402` and `C-403`. |
| **V-07** | Check for negative timeslot splits | Zero occurrences of `(` in `START_TIME` or `)` in `END_TIME` across both SQLite databases. |
| **V-08** | Verify Tutorial badges | All 15 tutorial cells store `STATUS = 'Tutorial'` and render `.status-tutorial` badges. |
