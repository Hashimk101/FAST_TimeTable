#!/usr/bin/env python3
"""
sync_faculty_to_supabase.py
===========================
FAST NUCES Faculty Timetable Ingestion & Synchronization Pipeline:
1. Parses 'Course Allocation - Fall-2026, School of Computing.xlsx' across all 4 sheets:
   ('Computing-Theory', 'Computing-Labs', 'S&H', 'MG').
2. Forward-fills merged cells (Course Codes, Course Titles, Credit Hours, Coordinators).
3. Translates Fall 2026 section codes using the exact formula:
   Batch Year = 26 - ((Semester - 1) // 2).
4. Maps full course titles to canonical timetable subjects in SQLite.
5. Matches teacher names to emails in 'frontend/data/faculty.bin' using strict
   token-set equality and normalized Levenshtein ratio (>= 0.92) to eliminate substring collisions.
6. Joins Theory classes from 'uni_timetable.db' and Lab classes from 'uni_timetable_lab.db'.
7. Pre-compiles clean weekly schedules grouped by day (Monday-Saturday).
8. Upserts to Supabase PostgreSQL, automatically incrementing version when schedule changes.
"""

import os
import sys
import re
import csv
import hmac
import io
import json
import base64
import hashlib
import shutil
import sqlite3
import tempfile
import time
import unicodedata
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any, Union
from datetime import datetime, timezone
from urllib.parse import quote

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, execute_values
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

import requests

from config import get_active_semester_config, get_database_url, is_ci_environment, validate_spreadsheet_id

# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_EXCEL_PATH = str(BASE_DIR / "Course Allocation - Fall-2026, School of Computing.xlsx")
FACULTY_BIN_PATH = str(BASE_DIR / "frontend" / "data" / "faculty.bin")
THEORY_DB_PATH = str(BASE_DIR / "uni_timetable.db")
LAB_DB_PATH = str(BASE_DIR / "uni_timetable_lab.db")
CREDENTIALS_PATH = str(BASE_DIR / "credentials.json")
TOKEN_PATH = str(BASE_DIR / "token.json")

MAX_XLSX_DOWNLOAD_BYTES = 15 * 1024 * 1024
MAX_ZIP_ENTRIES = 500
MAX_ZIP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 100.0
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

PARSED_ALLOCATION_KEYS = (
    "sheet",
    "is_lab",
    "course_code",
    "course_title",
    "credit_hours",
    "coordinator",
    "raw_section",
    "raw_instructor",
    "batch",
    "timetable_section",
    "canonical_subject",
)

ALLOCATION_SHEETS = ["Computing-Theory", "Computing-Labs", "S&H", "MG"]
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# Stopwords & Honorific Titles to strip during teacher matching
HONORIFIC_PATTERN = re.compile(
    r'^(dr|doctor|prof|professor|mr|ms|mrs|engr|syed|syeda|sheikh|pir|chaudhry|ch)\s+',
    re.IGNORECASE
)

# Explicit alias overrides for known institutional teacher naming variations
KNOWN_FACULTY_ALIASES = {
    "jawad hasan": "jawad.hassan@nu.edu.pk",
    "jawad hassan": "jawad.hassan@nu.edu.pk",
    "zirva": "zirva.shabbir@isb.nu.edu.pk",
    "zirva shabbir": "zirva.shabbir@isb.nu.edu.pk",
    "zirwa": "zirva.shabbir@isb.nu.edu.pk",
    "gul e zahra": "gul.zahra@isb.nu.edu.pk",
    "m ajmal": "muhammad.ajmal@nu.edu.pk",
    "m umer": "muhammad.umer@isb.nu.edu.pk",
    "maimoona": "maimoona.rasool@nu.edu.pk",
    "maimoona rasool": "maimoona.rasool@nu.edu.pk",
    "aisha ijaz": "aisha.ijaz@nu.edu.pk",
    "aisha": "aisha.ijaz@nu.edu.pk",
    "ghalia gohar": "ghalia.gohar@nu.edu.pk",
    "ghalia": "ghalia.gohar@nu.edu.pk",
    "hamda": "hamda.khan@nu.edu.pk",
    "momal": "momal.saleem@nu.edu.pk",
    "khubab": "khubab.ahmed@isb.nu.edu.pk",
    "ahsan": "ahsan.shakeel@isb.nu.edu.pk",
    "rubab": "rubab.zainab@isb.nu.edu.pk",
    "hafsa": "hafsa.waheed@isb.nu.edu.pk",
    "dilnawaz": "dilnawaz.khan@isb.nu.edu.pk",
    "saqib": "muhammad.saqib@isb.nu.edu.pk",
    "waqar": "waqar.ahmad@isb.nu.edu.pk",
    "nawafal waqar": "nawfal.waqar@isb.nu.edu.pk",
    "usman": "usman.ashraf@nu.edu.pk",
    "faisal": "faisal.rehman@isb.nu.edu.pk",
    "shah faisal": "shah.faisal@nu.edu.pk",
    "afaf": "afaf.ahmad@isb.nu.edu.pk",
    "sehrish hassan shigri": "sehrish.hassan@nu.edu.pk",
    "noor ul ain khattak": "noorul.ain@nu.edu.pk",
    "noorulain khattak": "noorul.ain@nu.edu.pk",
    "noor-ul-ain khattak": "noorul.ain@nu.edu.pk",
    "noor ul ain (cs)": "noorul.ain@nu.edu.pk",
    "noor ul ain (se)": "noor.ulain@isb.nu.edu.pk",
}

CANONICAL_FALLBACK_NAMES = {
    "mr. ahsan": "Mr. Ahsan Shakeel Malik",
    "ahsan": "Mr. Ahsan Shakeel Malik",
    "mr. khubab": "Mr. Khubab Ahmed",
    "khubab": "Mr. Khubab Ahmed",
    "ms. hafsa": "Ms. Hafsa Waheed",
    "hafsa": "Ms. Hafsa Waheed",
    "ms. rubab": "Ms. Syeda Rubab Zainab",
    "rubab": "Ms. Syeda Rubab Zainab",
    "ms. areej": "Ms. Areej",
    "areej": "Ms. Areej",
    "mr. saqib": "Mr. Muhammad Saqib",
    "saqib": "Mr. Muhammad Saqib",
    "mr. waqar": "Mr. Waqar Ahmad",
    "waqar": "Mr. Waqar Ahmad",
    "mr. dilnawaz": "Dr. Dilnawaz Khan",
    "dilnawaz": "Dr. Dilnawaz Khan",
    "mr. faisal": "Mr. Faisal ur Rehman",
    "faisal": "Mr. Faisal ur Rehman",
    "mr. afaf": "Ms. Afaf Ahmad",
    "afaf": "Ms. Afaf Ahmad",
    "mr. m.umer": "Mr. Muhammad Umer",
    "m.umer": "Mr. Muhammad Umer",
    "mumer": "Mr. Muhammad Umer",
    "mr ibrahim": "Dr. Muhammad Ibrahim",
    "ibrahim": "Dr. Muhammad Ibrahim",
    "dr usman": "Dr. Muhammad Usman Ashraf",
    "usman": "Dr. Muhammad Usman Ashraf",
    "ms momal": "Ms. Momal Saleem",
    "momal": "Ms. Momal Saleem",
    "dr hamda": "Dr. Hamda Khan",
    "hamda": "Dr. Hamda Khan",
    "dr mahboobullah": "Dr. Mahboobullah",
    "mahboobullah": "Dr. Mahboobullah",
    "ms. mahnoor": "Ms. Sayeda Mahnoor Ali",
    "mahnoor": "Ms. Sayeda Mahnoor Ali",
    "ms. maimoona": "Dr. Maimoona Rasool",
    "maimoona": "Dr. Maimoona Rasool",
    "ms. nimra": "Ms. Nimra",
    "nimra": "Ms. Nimra",
    "ms. zareen": "Ms. Zareen",
    "zareen": "Ms. Zareen",
    "ms. hina": "Ms. Hina",
    "hina": "Ms. Hina",
    "aisha": "Ms. Aisha Ijaz",
    "ghalia": "Ms. Ghalia Gohar",
    "zirwa": "Ms. Zirva Shabbir",
    "zirva": "Ms. Zirva Shabbir"
}

# Instructors in allocation sheet who are distinct visiting/different individuals despite sharing a surname
EXCLUDED_SUBSET_MATCHES = {
    "zareen",  # Ms. Zareen (teaches TBW) is distinct from Ms. Aseefa Zareen (teaches Pak Studies)
    "areej",   # Ms. Areej (teaches Func Eng Lab in S&H) is distinct from Ms. Areej Fatima (Cyber Security)
    "nimra",   # Ms. Nimra (teaches Func Eng/TBW in S&H) is distinct from Ms. Nimra Shahid (Computer Science)
    "hina",    # Ms. Hina (teaches Func Eng Lab in S&H) is distinct from Dr. Hina Ayaz (Computer Science)
}

# Known institutional canonical subject map
CANONICAL_SUBJECT_MAP = {
    # Theory Courses
    "programming fundamentals": "PF",
    "calculus & analytical geometry": "Calculus",
    "calculus and analytical geometry": "Calculus",
    "calculus": "Calculus",
    "functional english": "Func Eng",
    "ideology & constitution of pakistan": "Ideology of Pak",
    "ideology of pakistan": "Ideology of Pak",
    "islamic studies": "Islamic",
    "islamic studies / ethics": "Islamic",
    "civics & community engagement": "Civics",
    "civics and community engagement": "Civics",
    "applied physics": "AP",
    "object oriented programming": "OOP",
    "digital logic design": "DLD",
    "computer organization & assembly language": "COAL",
    "computer organization and assembly language": "COAL",
    "data structures": "Data St",
    "discrete structures": "Discrete",
    "linear algebra": "LA",
    "theory of automata": "Automata",
    "database systems": "DB",
    "operating systems": "OS",
    "design & analysis of algorithms": "Algo",
    "design and analysis of algorithms": "Algo",
    "analysis of algorithms": "Algo",
    "computer networks": "Comp Net",
    "artificial intelligence": "AI",
    "software construction & development": "S/w Const",
    "software construction and development": "S/w Const",
    "software engineering": "Fund of SE",
    "fundamentals of software engineering": "Fund of SE",
    "introduction to software engineering": "Intro to SE",
    "parallel & distributed computing": "PDC",
    "parallel and distributed computing": "PDC",
    "information security": "Info Sec",
    "cyber security": "Cy Sec",
    "technical & business writing": "TBW",
    "technical and business writing": "TBW",
    "machine learning": "ML",
    "deep learning": "Deep Learn",
    "natural language processing": "NLP",
    "generative ai": "Gen AI",
    "agentic ai": "Agentic AI",
    "applied computer vision": "App Comp Vision",
    "fundamentals of computer vision": "Fund of CV",
    "advanced computer vision": "Adv Computer Vision",
    "human computer interaction": "HCI",
    "applied human computer interaction": "App HCI",
    "software design & architecture": "SDA",
    "software design and architecture": "SDA",
    "software mobile application development": "SMD",
    "software quality engineering": "S/w Quality Engg",
    "software re-engineering": "S/w Re-Engg",
    "data warehousing & bi": "Data Ware & BI",
    "data warehousing and business intelligence": "Data Ware & BI",
    "introduction to data science": "Intro to DS",
    "data analysis & visualization": "DAV",
    "data analysis and visualization": "DAV",
    "data visualization": "Data Visualization",
    "methods in business research": "Business Research",
    "digital sustainability": "Digital Sustain",
    "ai-led transformation": "AI Led Transform",
    "embedded control for robotics": "Embed Robo",
    "edge computing": "Edge Comp",
    "security operations and administration": "Security Ops",
    "security operations & administration": "Security Ops",
    "applied information security": "Applied Info Sec",
    "statistical modelling": "Stat Modeling",
    "probability & statistics": "Prob & Stats",
    "probability and statistics": "Prob & Stats",
    "advanced statistics": "Adv Stats",
    "cloud computing": "Cloud Comp",
    "blockchain": "Blockchain",
    "game design and development": "Game Design",
    "fundamentals of software project management": "Fund of SPM",
    "computer architecture": "Comp Arch",
    "professional practices in it": "PPIT",
    "software for mobile devices": "SMD",

    # S&H / Humanities Courses (Excel titles → timetable DB subjects)
    "calculus & anlytical geometry": "Calculus",       # Excel typo variant
    "ideology and constitution of pakistan": "Ideology of Pak",
    "islamic studies/ethics": "Islamic",
    "understanding sirat un nabi": "Seerah",
    "understanding sirat-un-nabi": "Seerah",
    "understanding of holy quran-i": "UHQ-I&II",
    "understanding of holy quran-ii": "UHQ-II",
    "understanding of holy quran ii/ethics ii": "UHQ-II",
    "understanding of holy quran-i & ii": "UHQ-I&II",
    "pakistan studies": "Pak Studies",
    "arts and humanities and technology": "Arts & Humanities",
    "functional english- lab": "Func Eng Lab",         # Excel dash variant
    "functional english - lab": "Func Eng Lab",

    # Repeat/Elective/7th-sem Courses
    "data warehousing & business intelligence": "Data Ware & BI",
    "data warehousing and business intelligence": "Data Ware & BI",
    "digital sustainability": "Digital Sustain",
    "knowledge representation & reasoning": "Knowl Rep",
    "knowledge representation and reasoning": "Knowl Rep",
    "advacned statistics": "Adv Stats",                # Excel typo
    "web programming": "Web Prog",
    "fundamentals of data visualization": "Fund of Data Vis",
    "data visualization": "Data Visualization",
    "mlops": "MLOps",
    "deep learning for perception": "Deep Learn",
    "agentic artificial intelligence": "Agentic AI",
    "multiagent systems and game theory": "Multiagent Sys",
    "edge computing and intelligent systems": "Edge Comp",
    "information assurance": "Info Assur",
    "blockchain and cryptocurrency": "Blockchain",
    "blockchain technologies and applications": "Blockchain",
    "formal methods in software engineering": "Formal Methods",
    "process mining and simulation": "Process Mining",
    "software construction and develpment": "S/w Const",  # Excel typo
    "ai product development": "AI Prod Dev",
    "secure systems design": "Secure Sys",
    "prgramming for ai": "Prog for AI",                # Excel typo
    "security operations": "Security Ops",
    "vulnerability assessment": "Vulnerability Asses.",
    "data warehousing and business intelligence lab": "Data Ware & BI Lab",
    "data warehousing & business intelligence lab": "Data Ware & BI Lab",
    "vision based ai agent": "Vision Based AI Agent",

    # Labs
    "programming fundamentals lab": "PF Lab",
    "introduction to information & communication technologies": "IICT",
    "introduction to information and communication technologies": "IICT",
    "introduction to information & communication technologies lab": "IICT",
    "introduction to information and communication technologies lab": "IICT",
    "iict": "IICT",
    "iict lab": "IICT",
    "digital logic design lab": "DLD Lab",
    "object oriented programming lab": "OOP Lab",
    "data structures lab": "Data St Lab",
    "computer organization & assembly language lab": "COAL Lab",
    "computer organization and assembly language lab": "COAL Lab",
    "database systems lab": "DB Lab",
    "operating systems lab": "OS Lab",
    "computer networks lab": "Comp Net Lab",
    "software construction & development lab": "S/w Const Lab",
    "software construction and development lab": "S/w Const Lab",
    "software construction and development - lab": "S/w Const Lab",
    "artificial intelligence lab": "AI Lab",
    "machine learning lab": "ML Lab",
    "introduction to data science lab": "Intro to DS Lab",
    "data analysis & visualization lab": "DAV Lab",
    "data warehousing & bi lab": "Data Ware & BI Lab",
    "functional english lab": "Func Eng Lab",
    "programming for ai lab": "Prog for AI Lab",
    "programing for ai lab": "Prog for AI Lab",
    "prgramming for ai lab": "Prog for AI Lab",
    "security operations and administration lab": "Sec Ops",
    "security operations & administration lab": "Sec Ops",
    "vulnerability assessment lab": "Vulnerability Assesment Lab",

    # Graduate / MS Courses
    "applied programming": "Applied Programming MS",
    "research methodology": "Research Methodology",
    "programming for ai": "Prog for AI",
    "mathematics for computational intelligence": "Math for CI",
    "database and operating systems": "DB & OS",
    "data structures and algorithms": "Data St & Algo",
    "foundation of ai in health sciences": "Found of AI",
    "programming for digital health applications": "Prog for Digital Health",
    "foundation of health information system": "Found of Health Info Sys",
    "advanced operating systems": "Adv OS",
    "advanced analysis of algorithms": "Adv Algo",
    "advanced artificial intelligence": "Adv AI",
    "mathematical foundations of ai": "Math Foundations of AI",
    "advanced software architecture": "Adv S/w Arch",
    "advanced quality assurance": "Adv Quality Assur",
    "empirical software engineering": "Empirical S/w Engg",
    "engineering ai-based software": "Engg AI",
    "securing cloud computing": "Securing Cloud",
    "machine learning for cyber security": "CY & Net Security",
    "stat. & mathematical methods for data science": "Stat & Math",
    "data science tools and techniques": "DS Tools & Tech",
    "advanced topics in generative ai": "Adv Topics in Gen AI",
    "uhq_i&ii": "UHQ-I & II",
    "uhq-i&ii": "UHQ-I & II"
}

# =============================================================================
# 1. FACULTY REGISTRY DECODER & STRING MATCHING
# =============================================================================

def decode_faculty_bin(bin_path: str = FACULTY_BIN_PATH) -> List[Dict[str, Any]]:
    """Decodes the obfuscated static faculty binary file."""
    if not os.path.exists(bin_path):
        raise FileNotFoundError(f"Faculty binary file not found at: {bin_path}")
    with open(bin_path, "r", encoding="utf-8") as f:
        encoded_content = f.read().strip()
    decoded_reversed = base64.b64decode(encoded_content).decode("utf-8")
    raw_json = decoded_reversed[::-1]
    data = json.loads(raw_json)
    return data.get("faculty", [])

def normalize_person_name(name: str) -> Tuple[str, List[str]]:
    """
    Cleans a person name by removing honorifics, symbols, and whitespace.
    Returns (cleaned_joined_string, list_of_cleaned_tokens).
    """
    if not name:
        return "", []
    
    cleaned = re.sub(r'\(.*?\)', '', name).strip()
    cleaned = re.sub(r'[\.\-_/]', ' ', cleaned).strip()
    
    while True:
        m = HONORIFIC_PATTERN.match(cleaned)
        if m:
            cleaned = cleaned[m.end():].strip()
        else:
            break
            
    cleaned = re.sub(r'[^a-zA-Z\s]', '', cleaned).lower()
    tokens = [t for t in cleaned.split() if len(t) > 0]
    return " ".join(tokens), tokens

def levenshtein_distance(s1: str, s2: str) -> int:
    """Computes exact Wagner-Fischer edit distance."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1] + [0] * len(s2)
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row[j + 1] = min(insertions, deletions, substitutions)
        prev_row = curr_row
    return prev_row[-1]

def normalized_levenshtein_ratio(s1: str, s2: str) -> float:
    """Calculates normalized similarity in [0.0, 1.0]."""
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    return 1.0 - (levenshtein_distance(s1, s2) / max_len)

def disambiguate_candidates(
    candidates: List[Dict[str, Any]],
    discipline: str = "",
    is_lab: bool = False,
    department: str = "",
    course_title: str = ""
) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    disc_upper = (discipline or "").strip().upper()
    title_lower = (course_title or "").strip().lower()
    dept_lower = (department or "").strip().lower()

    # Issue 01: Explicit Ms. Noor Ul Ain Disambiguation
    # Check discipline ('BSE' vs 'BCS'/'BAI'), is_lab, and course_title
    # If discipline == 'BSE' or is_lab=True for SE AI lab ('AL2002' / 'Artificial Intelligence Lab'),
    # match noor.ulain@isb.nu.edu.pk (Lecturer/Instructor, SE).
    # If CS theory, match noorulain.khattak@isb.nu.edu.pk / noorul.ain@nu.edu.pk (Assistant Professor, CS).
    noor_candidates = [
        c for c in candidates 
        if "noor" in c.get("name", "").lower() and "ain" in c.get("name", "").lower()
    ]
    if len(noor_candidates) >= 2:
        is_se_lab = (
            disc_upper in ("BSE", "SE")
            or is_lab
            or any(term in title_lower for term in ("al2002", "artificial intelligence lab", "ai lab", "(se)"))
            or "software" in dept_lower
        )
        if is_se_lab and not (disc_upper in ("BCS", "CS", "BAI", "AI", "BCY", "CY", "BDS", "DS") and not is_lab):
            for c in noor_candidates:
                if c.get("email", "").lower().strip() == "noor.ulain@isb.nu.edu.pk" or "software" in c.get("dept", "").lower():
                    return c
        else:
            for c in noor_candidates:
                if c.get("email", "").lower().strip() in ("noorulain.khattak@isb.nu.edu.pk", "noorul.ain@nu.edu.pk") or "computer" in c.get("dept", "").lower():
                    return c

    # 1. Discipline / Department Match:
    # If discipline in ("SE", "BSE") or "(se)" in course_title.lower(): Prefer candidate with "software" in dept.lower()
    # If discipline in ("CS", "BCS") or "(cs)" in course_title.lower(): Prefer candidate with "computer" in dept.lower()
    # If discipline in ("AI", "BAI", "DS", "BDS") or "(ai)" in course_title.lower(): Prefer candidate with "artificial" in dept.lower()
    pref_by_dept = []
    if disc_upper in ("SE", "BSE") or "(se)" in title_lower or "software" in dept_lower:
        pref_by_dept = [c for c in candidates if "software" in c.get("dept", "").lower()]
    elif disc_upper in ("CS", "BCS") or "(cs)" in title_lower or "computer" in dept_lower:
        pref_by_dept = [c for c in candidates if "computer" in c.get("dept", "").lower()]
    elif disc_upper in ("AI", "BAI", "DS", "BDS") or "(ai)" in title_lower or "(ds)" in title_lower or "artificial" in dept_lower:
        pref_by_dept = [c for c in candidates if "artificial" in c.get("dept", "").lower()]

    if len(pref_by_dept) == 1:
        return pref_by_dept[0]

    pool = pref_by_dept if len(pref_by_dept) > 1 else candidates

    # 2. Designation / Lab Match:
    # If is_lab is True: Prefer candidates with desig == "Instructor"
    # If is_lab is False: Prefer candidates with desig in {"Assistant Professor", "Associate Professor", "Professor", "Lecturer"}
    if is_lab:
        lab_candidates = [c for c in pool if c.get("desig") == "Instructor"]
        if lab_candidates:
            return lab_candidates[0]
    else:
        theory_candidates = [
            c for c in pool 
            if c.get("desig") in {"Assistant Professor", "Associate Professor", "Professor", "Lecturer"}
        ]
        if theory_candidates:
            return theory_candidates[0]

    return pool[0]

def find_faculty_match(
    teacher_name: str, 
    faculty_roster: List[Dict[str, Any]], 
    threshold: float = 0.92,
    discipline: str = "",
    is_lab: bool = False,
    department: str = "",
    course_title: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Matches an Excel teacher name to an email record in faculty.bin.
    Enforces STRICT Token-Set Equality and Normalized Levenshtein (>= 0.92).
    Eliminates substring collisions (e.g. 'Ali' vs 'Muhammad Ali').
    Disambiguates duplicate name candidates using discipline, is_lab, department, and course_title.
    """
    clean_target, target_tokens = normalize_person_name(teacher_name)
    if not clean_target or not target_tokens:
        return None
        
    # 0. Check explicit known aliases
    if clean_target in KNOWN_FACULTY_ALIASES:
        target_email = KNOWN_FACULTY_ALIASES[clean_target]
        for fac in faculty_roster:
            if fac.get("email", "").lower().strip() == target_email:
                return fac

    target_set = set(target_tokens)
    target_sorted = " ".join(sorted(target_tokens))
    
    candidates = []
    for fac in faculty_roster:
        fac_name = fac.get("name", "")
        clean_fac, fac_tokens = normalize_person_name(fac_name)
        if not clean_fac or not fac_tokens:
            continue
            
        fac_set = set(fac_tokens)
        
        # 1. Exact string match after title stripping
        if clean_target == clean_fac:
            candidates.append(fac)
            continue

        # 2. Strict Token-Set Equality
        if target_set == fac_set:
            candidates.append(fac)
            continue

    if candidates:
        return disambiguate_candidates(
            candidates,
            discipline=discipline,
            is_lab=is_lab,
            department=department,
            course_title=course_title
        )

    # Check subset exclusions (e.g. 'zareen' != 'aseefa zareen')
    if clean_target in EXCLUDED_SUBSET_MATCHES:
        return None

    # 3. Unique Subset Match
    # Requires at least 2 tokens in target (e.g. 'Arshad Islam', 'Atif Jilani', 'Zaheer Sani')
    # Target tokens must be a strict subset of faculty tokens (target_set.issubset(fac_set))
    # NEVER allow fac_set.issubset(target_set) because that means target has an extra surname like 'Shiekh' or 'Farooq'!
    if len(target_tokens) >= 2:
        subset_matches = []
        for fac in faculty_roster:
            clean_fac, fac_tokens = normalize_person_name(fac.get("name", ""))
            fac_set = set(fac_tokens)
            if target_set.issubset(fac_set) and len(fac_set) > len(target_set):
                if target_tokens[0] in fac_tokens:
                    subset_matches.append(fac)
        
        if len(subset_matches) == 1:
            return subset_matches[0]
        elif len(subset_matches) > 1:
            return disambiguate_candidates(
                subset_matches,
                discipline=discipline,
                is_lab=is_lab,
                department=department,
                course_title=course_title
            )

    # 4. Fuzzy Match (Levenshtein ratio >= 0.88, requires target to have >= 2 tokens)
    if len(target_tokens) >= 2:
        best_facs = []
        best_ratio = 0.0
        for fac in faculty_roster:
            clean_fac, fac_tokens = normalize_person_name(fac.get("name", ""))
            if len(fac_tokens) < 2:
                continue
            fac_sorted = " ".join(sorted(fac_tokens))
            ratio = normalized_levenshtein_ratio(target_sorted, fac_sorted)
            if ratio > best_ratio:
                best_ratio = ratio
                best_facs = [fac]
            elif ratio == best_ratio and ratio >= 0.88:
                best_facs.append(fac)

        if best_ratio >= 0.88 and best_facs:
            return disambiguate_candidates(
                best_facs,
                discipline=discipline,
                is_lab=is_lab,
                department=department,
                course_title=course_title
            )

    return None

# =============================================================================
# 2. SECTION TRANSLATOR & CANONICAL SUBJECT RESOLVER
# =============================================================================

def translate_section_code(raw_sec: str, year: int = 2026, season: str = "fall") -> Dict[str, Any]:
    """
    Translates course allocation Excel section codes into timetable section codes
    and maps them to the appropriate student batch.

    Dynamic Batch Algebra:
      - Fall: Base year beta = year % 100 (e.g. Fall 2026 -> 26)
      - Spring / Summer: Base year beta = (year % 100) - 1 (e.g. Spring 2027 -> 26)
      - Batch Year = beta - ((semester - 1) // 2)

    Examples:
      Fall 2026:
        BCS-1A  -> Batch: 'BS 26 CS', Section: 'CS-A'
        BAI-3B  -> Batch: 'BS 25 AI', Section: 'AI-B'
        BSE-5C  -> Batch: 'BS 24 SE', Section: 'SE-C'
        BCY-7A  -> Batch: 'BS 23 CY', Section: 'CY-A'
      Spring 2027:
        BCS-2A  -> Batch: 'BS 26 CS', Section: 'CS-A'
        BAI-4B  -> Batch: 'BS 25 AI', Section: 'AI-B'
        BSE-6C  -> Batch: 'BS 24 SE', Section: 'SE-C'
        BCY-8A  -> Batch: 'BS 23 CY', Section: 'CY-A'
      Repeats and special cases:
        BCS-1A1 -> Batch: 'BS 26 CS', Section: 'CS-A' (Lab group 1 stripped)
        BSR-7A  -> Batch: 'BS 23 CS', Section: 'CS-Robo'
        BCS-9A  -> Batch: 'BS Repeat Courses', Section: 'CS-A'
    """
    sec = str(raw_sec).strip()
    result = {
        "raw_section": sec,
        "batch": None,
        "timetable_section": sec,
        "is_undergraduate": False,
        "semester": None,
        "discipline": None
    }
    
    # 1. Undergraduate regex: B<DISC>-<SEM><SEC>[<SUB>]
    m_bs = re.match(r'^B([A-Z]{2,3})-(\d)([A-Z])(\d)?$', sec, re.IGNORECASE)
    if m_bs:
        disc = m_bs.group(1).upper()
        sem = int(m_bs.group(2))
        sec_letter = m_bs.group(3).upper()
        
        season_lower = (season or "fall").lower().strip()
        base_year = (year % 100) if season_lower == "fall" else ((year % 100) - 1)
        batch_year = base_year - ((sem - 1) // 2)
        
        result["is_undergraduate"] = True
        result["semester"] = sem
        result["discipline"] = disc
        
        # Special case: BSR-7A -> BS Robotics mapped to CS-Robo under BS 23 CS
        if disc == "SR":
            result["batch"] = f"BS {batch_year} CS"
            result["timetable_section"] = "CS-Robo"
            return result

        # Repeats (Semester >= 8)
        if sem >= 9:
            result["batch"] = "BS Repeat Courses"
            result["timetable_section"] = f"{disc}-{sec_letter}"
            return result

        result["batch"] = f"BS {batch_year} {disc}"
        result["timetable_section"] = f"{disc}-{sec_letter}"
        return result

    # 2. Graduate / MS Programs: MCS-A, MSE-A, MAI-A, MCI-A, MDS-A, MCY-A, MS-AIHS-A, MS-A, etc.
    sec_upper = sec.upper()
    if sec_upper.startswith("MS-AIHS"):
        result["discipline"] = "AIHS"
        result["batch"] = "MS AI in Health Sciences"
        result["timetable_section"] = sec
        return result
    elif sec_upper.startswith("MS-") or sec_upper == "MS":
        result["discipline"] = "MS"
        result["batch"] = "MS Electives (All Prgrms)"
        result["timetable_section"] = sec
        return result

    m_ms = re.match(r'^M([A-Z]{2,4})-([A-Z0-9]+)$', sec, re.IGNORECASE)
    if m_ms:
        ms_disc = m_ms.group(1).upper()
        disc_map = {
            "CS": "MS CS",
            "SE": "MS SE",
            "AI": "MS AI",
            "CY": "MS CY",
            "DS": "MS DS",
            "CI": "MS Computational Intelligence",
            "AIHS": "MS AI in Health Sciences",
        }
        result["discipline"] = ms_disc
        result["batch"] = disc_map.get(ms_disc, f"MS {ms_disc}")
        result["timetable_section"] = sec
        return result

    # 3. PhD Programs: PCS, PCS-A, PCS-B, PHD-A, PHD-C
    if sec_upper.startswith("PCS") or sec_upper.startswith("PHD"):
        result["discipline"] = "PhD"
        result["batch"] = "PhD (Computing)"
        result["timetable_section"] = sec
        return result

    return result

def format_clean_section(sec_str: str) -> str:
    """
    Issue 09: Cleans raw combined or slashed section strings into clean comma-separated sections.
    Examples:
      'AI/DS-A'  -> 'AI-A, DS-A'
      'CS/CY-A'  -> 'CS-A, CY-A'
      'CS-A&B'   -> 'CS-A, CS-B'
      'AI/DS/CS' -> 'AI, DS, CS'
    """
    if not sec_str:
        return ""
    sec_str = sec_str.strip()
    if "/" in sec_str:
        m = re.match(r'^([A-Z/]+)-([A-Z0-9]+)$', sec_str)
        if m:
            discs = m.group(1).split('/')
            sec_letter = m.group(2)
            return ", ".join(f"{d.strip()}-{sec_letter}" for d in discs if d.strip())
        parts = [p.strip() for p in sec_str.split('/') if p.strip()]
        return ", ".join(parts)
    if "&" in sec_str:
        m = re.match(r'^([A-Z]+)-([A-Z0-9]+)&([A-Z0-9]+)$', sec_str)
        if m:
            disc = m.group(1)
            return f"{disc}-{m.group(2)}, {disc}-{m.group(3)}"
        parts = [p.strip() for p in sec_str.split('&') if p.strip()]
        return ", ".join(parts)
    return sec_str

def resolve_canonical_subject(course_title: str, course_code: str = "", is_lab: bool = False) -> str:
    """Maps full course title to its canonical timetable subject shorthand."""
    raw_title = (course_title or "").strip()
    if not raw_title:
        return ""

    clean_title = re.sub(r'\(.*?\)', '', raw_title).strip()
    clean_title = re.sub(r'\s+for\s+Batch-.*$', '', clean_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r'\s+', ' ', clean_title).lower()

    if is_lab and not clean_title.endswith("lab"):
        clean_title += " lab"

    # 1. Exact Dictionary Match
    if clean_title in CANONICAL_SUBJECT_MAP:
        return CANONICAL_SUBJECT_MAP[clean_title]

    # 2. Lookup without 'lab' appended
    base_title = re.sub(r'\s+lab$', '', clean_title).strip()
    if base_title in CANONICAL_SUBJECT_MAP:
        canonical = CANONICAL_SUBJECT_MAP[base_title]
        return f"{canonical} Lab" if is_lab and not canonical.endswith("Lab") else canonical

    # 3. Fallback: Acronym Generation
    words = [w for w in re.split(r'[\s\-_]+', base_title) if w and w not in {"and", "of", "to", "in", "for", "the"}]
    if len(words) == 1:
        acronym = words[0].capitalize()
    else:
        acronym = "".join(w[0].upper() for w in words)
        
    return f"{acronym} Lab" if is_lab else acronym

# =============================================================================
# 3. EXCEL ALLOCATION INGESTION (FORWARD-FILLING MERGED CELLS)
# =============================================================================

def read_course_allocations(excel_path: str = DEFAULT_EXCEL_PATH, year: int = 2026, season: str = "fall") -> List[Dict[str, Any]]:
    """
    Parses all 4 sheets in the Course Allocation workbook:
    - 'Computing-Theory', 'Computing-Labs', 'S&H', 'MG'
    Forward-fills vertically merged cells.
    """
    if openpyxl is None:
        raise RuntimeError("openpyxl is required to parse Excel course allocations.")
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Course Allocation workbook not found at: {excel_path}")

    season_lower = (season or "fall").lower().strip()
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    allocations = []

    IGNORED_INSTRUCTORS = {
        "fyp committee", "msrc", "tbd", "none", "nil", "to be announced", 
        "course instructor", "instructor"
    }

    for sheet_name in ALLOCATION_SHEETS:
        if sheet_name not in wb.sheetnames:
            print(f"[WARN] Sheet '{sheet_name}' not found in Excel workbook. Skipping.")
            continue

        ws = wb[sheet_name]
        is_lab = "lab" in sheet_name.lower()
        print(f"Reading allocation sheet: '{sheet_name}' (is_lab={is_lab})...")

        header_row = 3
        for r in range(1, 10):
            vals = [str(ws.cell(r, c).value or '').strip().lower() for c in range(1, 10)]
            if "code" in vals and "course" in vals:
                header_row = r
                break

        curr_code = ""
        curr_course = ""
        curr_chs = 3.0 if not is_lab else 1.0
        curr_coordinator = ""

        for row_idx in range(header_row + 1, ws.max_row + 1):
            cell_code = ws.cell(row_idx, 2).value
            cell_course = ws.cell(row_idx, 3).value
            cell_chs = ws.cell(row_idx, 4).value
            cell_section = ws.cell(row_idx, 5).value
            cell_instructor = ws.cell(row_idx, 6).value
            cell_coordinator = ws.cell(row_idx, 7).value

            if cell_code and str(cell_code).strip():
                curr_code = str(cell_code).strip()
            if cell_course and str(cell_course).strip():
                curr_course = str(cell_course).strip()
            if cell_chs is not None:
                try:
                    curr_chs = float(cell_chs)
                except ValueError:
                    pass
            if cell_coordinator and str(cell_coordinator).strip():
                curr_coordinator = str(cell_coordinator).strip()

            if not cell_section or not cell_instructor:
                continue

            sec_str = str(cell_section).strip()
            instr_str = str(cell_instructor).strip()

            if instr_str.lower() in IGNORED_INSTRUCTORS or sec_str.lower() in {"section", "nil"}:
                continue

            sec_info = translate_section_code(sec_str, year=year, season=season_lower)
            course_is_lab = is_lab or "lab" in curr_course.lower()
            canonical_subj = resolve_canonical_subject(curr_course, curr_code, is_lab=course_is_lab)

            allocations.append({
                "sheet": sheet_name,
                "is_lab": course_is_lab,
                "course_code": curr_code,
                "course_title": curr_course,
                "credit_hours": curr_chs,
                "coordinator": curr_coordinator,
                "raw_section": sec_str,
                "raw_instructor": instr_str,
                "batch": sec_info["batch"],
                "timetable_section": sec_info["timetable_section"],
                "canonical_subject": canonical_subj
            })

    print(f"Loaded {len(allocations)} total valid course section allocations.")
    return allocations

# =============================================================================
# 4. TIMETABLE JOIN & PRE-COMPILATION ENGINE
# =============================================================================

class ReconciliationAuditor:
    """
    Tracks and audits discrepancies between Course Allocation workbooks and Room Timetables:
    1. Unmatched course allocations (courses with 0 slots on schedule).
    2. Orphaned timetable slots (scheduled rooms with no teacher assigned).
    3. Acronym and subject typo suggestions.
    4. Visiting/external instructors with synthetic accounts.
    """
    def __init__(self, semester_id: str = "2026-fall"):
        self.semester_id = semester_id
        self.total_allocations: int = 0
        self.matched_allocations: int = 0
        self.unmatched_allocations: List[Dict[str, Any]] = []
        self.claimed_slot_keys: Set[Tuple[bool, int]] = set()  # (is_lab, rowid)
        self.orphaned_slots: List[Dict[str, Any]] = []
        self.visiting_faculty: List[str] = []
        self.total_db_slots: int = 0
        self.claimed_db_slots_count: int = 0

    def record_claimed_slot(self, is_lab: bool, rowid: int):
        self.claimed_slot_keys.add((is_lab, rowid))

    def record_allocation_matched(self, alloc: Dict[str, Any], fac_info: Dict[str, Any], email: str, rows: List[Any], is_lab: bool):
        self.total_allocations += 1
        self.matched_allocations += 1

    def record_allocation_unmatched(self, alloc: Dict[str, Any], fac_info: Dict[str, Any], email: str, cur_theory: sqlite3.Cursor, cur_lab: sqlite3.Cursor):
        self.total_allocations += 1
        c_code = alloc.get("course_code") or ""
        c_title = alloc.get("course_title") or ""
        b_name = alloc.get("batch") or ""
        sec_name = str(alloc.get("timetable_section") or "").strip()
        canonical_subj = str(alloc.get("canonical_subject") or "").strip()
        is_lab = bool(alloc.get("is_lab", False))
        sheet = alloc.get("sheet", "")
        instr_name = fac_info.get("name") or alloc.get("raw_instructor", "")

        is_research = any(term in c_title.lower() for term in ["thesis", "final year project", "fyp", "project-i", "project-ii"])
        severity = "INFO" if is_research else "WARNING"
        diag = "Final Year Project / Thesis (independent study, typically not assigned classroom lecture slots)" if is_research else "No timetable slots found for this course, section, and batch combination"

        candidate_cursor = cur_lab if is_lab else cur_theory
        suggestion = ""
        if not is_research and b_name:
            try:
                candidate_cursor.execute("SELECT DISTINCT SUBJECT FROM timetable WHERE BATCH = ? LIMIT 50", (b_name,))
                subjs = [r[0] for r in candidate_cursor.fetchall() if r[0]]
                best_match = None
                best_score = 0.0
                for s in subjs:
                    score = normalized_levenshtein_ratio(canonical_subj.lower(), str(s).lower())
                    if score > best_score and score >= 0.5:
                        best_score = score
                        best_match = str(s)
                if best_match:
                    suggestion = f"Timetable has subject '{best_match}' in batch '{b_name}' (similarity {int(best_score*100)}%). Verify CANONICAL_SUBJECT_MAP."
            except Exception:
                pass

        if not suggestion and not is_research:
            suggestion = "Verify if section was scheduled on timetable sheet or if batch code matches."

        self.unmatched_allocations.append({
            "category": "UNMATCHED_ALLOCATION",
            "severity": severity,
            "instructor_name": instr_name,
            "instructor_email": email,
            "department": sheet,
            "course_code": c_code,
            "course_title": c_title,
            "canonical_subject": canonical_subj,
            "batch": b_name,
            "section": sec_name,
            "is_lab": is_lab,
            "details": diag,
            "suggested_action": suggestion
        })

    def record_unmatched_instructors(self, instructors: Set[str]):
        self.visiting_faculty = sorted(list(instructors))

    def finalize(self, cur_theory: sqlite3.Cursor, cur_lab: sqlite3.Cursor, semester_id: str):
        self.semester_id = semester_id
        for is_lab, cur, loc_col in [(False, cur_theory, "CLASSROOM"), (True, cur_lab, "LAB")]:
            cur.execute(f"SELECT ID, DAY, START_TIME, END_TIME, SUBJECT, {loc_col} AS LOCATION, SECTION, BATCH, STATUS FROM timetable")
            all_rows = cur.fetchall()
            self.total_db_slots += len(all_rows)
            for r in all_rows:
                key = (is_lab, r["ID"])
                if key not in self.claimed_slot_keys:
                    raw_status = str(r["STATUS"] or "").strip()
                    is_cancelled = "cancel" in raw_status.lower() if raw_status else False
                    self.orphaned_slots.append({
                        "category": "ORPHANED_TIMETABLE_SLOT",
                        "severity": "INFO" if is_cancelled else "MEDIUM",
                        "type": "Lab" if is_lab else "Classroom",
                        "day": r["DAY"],
                        "start_time": r["START_TIME"],
                        "end_time": r["END_TIME"],
                        "subject": r["SUBJECT"],
                        "location": r["LOCATION"] or "",
                        "section": r["SECTION"] or "",
                        "batch": r["BATCH"] or "",
                        "status": r["STATUS"] or "Regular",
                        "details": "Classroom slot exists on room timetable, but no faculty member in allocation sheet was assigned to this slot.",
                        "suggested_action": "Check if an instructor should be assigned in allocation workbook or if this is an open lab/cancelled slot."
                    })
        self.claimed_db_slots_count = len(self.claimed_slot_keys)

    def get_summary_dict(self) -> Dict[str, Any]:
        match_rate = (self.matched_allocations / self.total_allocations * 100.0) if self.total_allocations > 0 else 0.0
        coverage_rate = (self.claimed_db_slots_count / self.total_db_slots * 100.0) if self.total_db_slots > 0 else 0.0
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "semester_id": self.semester_id,
            "metrics": {
                "total_allocations": self.total_allocations,
                "matched_allocations": self.matched_allocations,
                "unmatched_allocations": len(self.unmatched_allocations),
                "allocation_match_rate_pct": round(match_rate, 2),
                "total_timetable_slots": self.total_db_slots,
                "claimed_slots": self.claimed_db_slots_count,
                "orphaned_slots": len(self.orphaned_slots),
                "timetable_coverage_pct": round(coverage_rate, 2),
                "visiting_faculty_count": len(self.visiting_faculty)
            },
            "unmatched_allocations_count": len(self.unmatched_allocations),
            "orphaned_slots_count": len(self.orphaned_slots),
            "visiting_faculty_sample": self.visiting_faculty[:10]
        }

    def to_csv_string(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Category",
            "Severity",
            "Instructor Name",
            "Instructor Email",
            "Department",
            "Course Code",
            "Course Title",
            "Canonical Subject",
            "Batch",
            "Section",
            "Is Lab",
            "Day",
            "Time Window",
            "Location",
            "Details",
            "Suggested Action"
        ])
        for u in self.unmatched_allocations:
            writer.writerow([
                u["category"],
                u["severity"],
                u["instructor_name"],
                u["instructor_email"],
                u["department"],
                u["course_code"],
                u["course_title"],
                u["canonical_subject"],
                u["batch"],
                u["section"],
                "Yes" if u["is_lab"] else "No",
                "",
                "",
                "",
                u["details"],
                u["suggested_action"]
            ])
        for o in self.orphaned_slots:
            writer.writerow([
                o["category"],
                o["severity"],
                "",
                "",
                "",
                "",
                "",
                o["subject"],
                o["batch"],
                o["section"],
                "Yes" if o["type"] == "Lab" else "No",
                o["day"],
                f"{o['start_time']} - {o['end_time']}",
                o["location"],
                o["details"],
                o["suggested_action"]
            ])
        return buf.getvalue()

    def export_csv(self, filepath: str):
        csv_content = self.to_csv_string()
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            f.write(csv_content)

    def export_json(self, filepath: str):
        summary = self.get_summary_dict()
        with open(filepath, mode="w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    def print_summary(self):
        metrics = self.get_summary_dict()["metrics"]
        print("\n" + "=" * 80)
        print("📊 INGESTION RECONCILIATION & AUDIT REPORT")
        print("=" * 80)
        print(f"Target Semester:                {self.semester_id}")
        print(f"Total Allocations in Workbook:  {metrics['total_allocations']}")
        print(f"  ✅ Successfully Mapped:       {metrics['matched_allocations']} ({metrics['allocation_match_rate_pct']}%)")
        print(f"  ⚠️  Unmatched Allocations:      {metrics['unmatched_allocations']} ({round(100 - metrics['allocation_match_rate_pct'], 2)}%)")
        print("-" * 80)
        print(f"Total Timetable Slots in DB:    {metrics['total_timetable_slots']}")
        print(f"  ✅ Claimed by Faculty:        {metrics['claimed_slots']} ({metrics['timetable_coverage_pct']}%)")
        print(f"  ⚠️  Orphaned Slots (No Staff): {metrics['orphaned_slots']} ({round(100 - metrics['timetable_coverage_pct'], 2)}%)")
        print("-" * 80)
        print(f"Visiting/External Instructors:  {metrics['visiting_faculty_count']}")
        print("=" * 80 + "\n")


def _parse_time_minutes(t_str: str) -> int:
    """Converts a 12h/university timetable time string into sortable minutes from midnight."""
    try:
        parts = str(t_str or "").split(":")
        h, m = int(parts[0]), int(parts[1])
        if (1 <= h <= 7) or (h == 8 and m < 30):
            h += 12
        return h * 60 + m
    except Exception:
        return 0


def _compute_schedule_hash(weekly_schedule: Dict[str, Any], courses_summary: List[Dict[str, Any]]) -> str:
    """Computes deterministic SHA-256 hash over schedule and courses manifest."""
    payload = {
        "schedule": weekly_schedule,
        "courses": courses_summary,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _is_custom_slot(slot: Any) -> bool:
    """Returns True if a schedule slot entry represents a legacy user-created custom activity."""
    if not isinstance(slot, dict):
        return False
    return (
        slot.get("isCustom") is True
        or bool(slot.get("customCategory"))
        or str(slot.get("id", "")).startswith("act")
    )


def compute_slot_uid(
    semester_id: str,
    day: str,
    start_time: str,
    subject: str,
    clean_sec: str,
    final_is_lab: bool,
) -> str:
    """Computes deterministic 12-char slot_uid for Layer 1 official slots."""
    raw_key = f"{semester_id}|{day}|{start_time}|{subject}|{clean_sec}|{final_is_lab}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12]


def _build_subject_sql_condition(
    canonical_subj: str,
    is_lab: bool = False
) -> Tuple[str, Tuple[str, ...], str, Tuple[str, ...]]:
    """
    Builds parameterized SQL conditions for full and blank-section timetable lookups.
    Enforces strict boundary matching on short acronyms (<= 3 chars, e.g. LA vs Lab, SMD vs SMD Nov 27)
    and prevents Theory allocations (is_lab=False) from matching rescheduled Lab cells in theory rooms.
    """
    base_subj = canonical_subj.replace(" Lab", "").strip() if canonical_subj else ""
    lab_guard = " AND LOWER(SUBJECT) NOT LIKE '%lab%'" if (not is_lab and "lab" not in canonical_subj.lower()) else ""

    if canonical_subj in ("UHQ-II", "UHQ-I&II", "UHQ-I & II"):
        subj_cond = f"((SUBJECT = ? OR SUBJECT = ? OR SUBJECT = ? OR SUBJECT LIKE ? OR SUBJECT LIKE ?){lab_guard})"
        subj_params = ("UHQ-II", "UHQ-I&II", "UHQ-I & II", "%UHQ-II%", "%UHQ-I%II%")
        return subj_cond, subj_params, subj_cond, subj_params

    if len(canonical_subj) <= 3:
        subj_cond = f"((SUBJECT = ? OR SUBJECT = ? OR SUBJECT LIKE ?){lab_guard})"
        subj_params = (canonical_subj, base_subj, f"{canonical_subj} %")
        blank_cond = f"((SUBJECT = ? OR SUBJECT LIKE ?){lab_guard})"
        blank_params = (canonical_subj, f"{canonical_subj} %")
        return subj_cond, subj_params, blank_cond, blank_params

    subj_cond = f"((SUBJECT = ? OR SUBJECT LIKE ? OR SUBJECT = ? OR SUBJECT LIKE ?){lab_guard})"
    subj_params = (canonical_subj, f"%{canonical_subj}%", base_subj, f"%{base_subj}%")
    blank_cond = f"((SUBJECT = ? OR SUBJECT LIKE ?){lab_guard})"
    blank_params = (canonical_subj, f"%{canonical_subj}%")
    return subj_cond, subj_params, blank_cond, blank_params


def _query_timetable_slots(
    cur_theory: sqlite3.Cursor,
    cur_lab: sqlite3.Cursor,
    b_name: str,
    sec_name: str,
    canonical_subj: str,
    is_lab: bool
) -> Tuple[List[sqlite3.Row], bool]:
    """
    Shared slot resolution cascade used by both full Excel ingestion and continuous DB sync.
    Strictly isolates Theory vs Lab databases (Issue 10).
    """
    if not canonical_subj:
        return [], is_lab

    subj_cond, subj_params, blank_cond, blank_params = _build_subject_sql_condition(canonical_subj, is_lab=is_lab)
    disc = sec_name.split("-")[0] if (sec_name and "-" in sec_name) else ""
    letter = sec_name.split("-")[1] if (sec_name and "-" in sec_name) else ""

    target_cursor, location_col, actual_lab = (
        (cur_lab, "LAB", True) if is_lab else (cur_theory, "CLASSROOM", False)
    )
    select_clause = (
        f"SELECT ID, DAY, START_TIME, END_TIME, SUBJECT, {location_col} AS LOCATION, "
        f"SECTION, BATCH, STATUS FROM timetable"
    )

    queries_to_try = []

    if b_name:
        if sec_name:
            queries_to_try.append({
                "query": f"{select_clause} WHERE BATCH = ? AND (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
                "params": (b_name, sec_name, f"%{sec_name}%") + subj_params
            })
        if disc and letter:
            queries_to_try.append({
                "query": f"{select_clause} WHERE BATCH = ? AND SECTION LIKE ? AND SECTION LIKE ? AND {subj_cond}",
                "params": (b_name, f"%{disc}%", f"%{letter}%") + subj_params
            })
        # Exact batch with blank/null section (open pool senior electives e.g. Fund of SPM, SMD, Agentic AI)
        queries_to_try.append({
            "query": f"{select_clause} WHERE BATCH = ? AND (SECTION = '' OR SECTION IS NULL) AND {blank_cond}",
            "params": (b_name,) + blank_params
        })
        queries_to_try.append({
            "query": f"{select_clause} WHERE BATCH = ? AND (SECTION = '' OR SECTION IS NULL) AND {subj_cond}",
            "params": (b_name,) + subj_params
        })
        # Fallback to 'BS Repeat Courses'
        if sec_name:
            queries_to_try.append({
                "query": f"{select_clause} WHERE BATCH = 'BS Repeat Courses' AND (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
                "params": (sec_name, f"%{sec_name}%") + subj_params
            })
        if disc and letter:
            queries_to_try.append({
                "query": f"{select_clause} WHERE BATCH = 'BS Repeat Courses' AND SECTION LIKE ? AND SECTION LIKE ? AND {subj_cond}",
                "params": (f"%{disc}%", f"%{letter}%") + subj_params
            })
        queries_to_try.append({
            "query": f"{select_clause} WHERE BATCH = 'BS Repeat Courses' AND (SECTION = '' OR SECTION IS NULL) AND {subj_cond}",
            "params": subj_params
        })
        # Graduate / MS / PhD fallback
        if b_name.startswith("MS") or b_name.startswith("PhD"):
            if sec_name:
                queries_to_try.append({
                    "query": f"{select_clause} WHERE (BATCH = 'MS Electives (All Prgrms)' OR BATCH LIKE 'MS%' OR BATCH LIKE 'PhD%') AND (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
                    "params": (sec_name, f"%{sec_name}%") + subj_params
                })
            queries_to_try.append({
                "query": f"{select_clause} WHERE (BATCH = 'MS Electives (All Prgrms)' OR BATCH LIKE 'MS%' OR BATCH LIKE 'PhD%') AND {subj_cond}",
                "params": subj_params
            })

    # Batch-agnostic fallbacks (also enables legacy continuous-sync recovery when batch was unrecorded)
    if sec_name:
        queries_to_try.append({
            "query": f"{select_clause} WHERE (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
            "params": (sec_name, f"%{sec_name}%") + subj_params
        })
    if disc and letter:
        queries_to_try.append({
            "query": f"{select_clause} WHERE SECTION LIKE ? AND SECTION LIKE ? AND {subj_cond}",
            "params": (f"%{disc}%", f"%{letter}%") + subj_params
        })
    queries_to_try.append({
        "query": f"{select_clause} WHERE (SECTION = '' OR SECTION IS NULL) AND {blank_cond}",
        "params": blank_params
    })
    queries_to_try.append({
        "query": f"{select_clause} WHERE (SECTION = '' OR SECTION IS NULL) AND {subj_cond}",
        "params": subj_params
    })

    for attempt in queries_to_try:
        target_cursor.execute(attempt["query"], attempt["params"])
        fetched = target_cursor.fetchall()
        if fetched:
            return fetched, actual_lab

    return [], is_lab


def _merge_slot_into_weekly_schedule(
    weekly_schedule: Dict[str, List[Dict[str, Any]]],
    row: sqlite3.Row,
    c_code: str,
    c_title: str,
    sec_name: str,
    b_name: str,
    final_is_lab: bool,
    semester_id: str = "2026-fall",
) -> int:
    """Appends or merges a matched SQLite row into weekly_schedule. Returns 1 if added, 0 if merged/skipped."""
    day = row["DAY"]
    if day not in weekly_schedule:
        return 0

    raw_status = str(row["STATUS"] or "").strip()
    is_cancelled = "cancel" in raw_status.lower() if raw_status else False
    clean_sec = sec_name if sec_name else format_clean_section(str(row["SECTION"] or ""))
    slot_uid = compute_slot_uid(
        semester_id,
        day,
        row["START_TIME"],
        row["SUBJECT"],
        clean_sec,
        final_is_lab,
    )

    slot_entry = {
        "id": slot_uid,
        "slot_uid": slot_uid,
        "start_time": row["START_TIME"],
        "end_time": row["END_TIME"],
        "subject": row["SUBJECT"],
        "course_name": c_title,
        "course_code": c_code,
        "location": row["LOCATION"] or "",
        "section": clean_sec,
        "batch": row["BATCH"] or b_name or "",
        "is_lab": final_is_lab,
        "status": row["STATUS"],
        "is_cancelled": is_cancelled,
    }

    for existing in weekly_schedule[day]:
        if (
            existing.get("start_time") == slot_entry["start_time"]
            and existing.get("end_time") == slot_entry["end_time"]
            and existing.get("subject") == slot_entry["subject"]
        ):
            if clean_sec:
                existing_secs = [s.strip() for s in str(existing.get("section") or "").split(",") if s.strip()]
                for s_part in clean_sec.split(","):
                    s_part = s_part.strip()
                    if s_part and s_part not in existing_secs:
                        existing_secs.append(s_part)
                existing["section"] = ", ".join(sorted(existing_secs))
                merged_uid = compute_slot_uid(
                    semester_id,
                    day,
                    existing["start_time"],
                    existing["subject"],
                    existing["section"],
                    bool(existing.get("is_lab", final_is_lab)),
                )
                existing["id"] = merged_uid
                existing["slot_uid"] = merged_uid
            if is_cancelled:
                existing["is_cancelled"] = True
            return 0

    weekly_schedule[day].append(slot_entry)
    return 1


def verify_compiled_records_integrity(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Post-compilation invariant checker: flags any non-FYP/Thesis allocated course
    that resulted in 0 scheduled slots so missing courses are surfaced immediately.
    """
    anomalies: List[Dict[str, Any]] = []
    for rec in records:
        sched = rec.get("schedule") or {}
        courses = rec.get("courses") or []
        all_slots = [
            s for d in DAYS_OF_WEEK for s in (sched.get(d, []) if isinstance(sched, dict) else [])
            if isinstance(s, dict) and not _is_custom_slot(s)
        ]
        for course in courses:
            c_code = str(course.get("course_code") or "")
            c_name = str(course.get("course_name") or "")
            c_subj = str(course.get("canonical_subject") or "").lower()
            is_lab = bool(course.get("is_lab", False))
            if any(k in c_name.lower() or k in c_subj for k in ("final year project", "thesis", "fyp")):
                continue
            matched = False
            for s in all_slots:
                if bool(s.get("is_lab", False)) != is_lab:
                    continue
                s_code = str(s.get("course_code") or "")
                s_subj = str(s.get("subject") or "").lower()
                if (c_code and s_code == c_code) or (
                    c_subj and (c_subj in s_subj or s_subj in c_subj or ("uhq" in c_subj and "uhq" in s_subj))
                ):
                    matched = True
                    break
            if not matched:
                anomalies.append({
                    "name": rec.get("name"),
                    "email": rec.get("email"),
                    "course_code": c_code,
                    "course_name": c_name,
                    "canonical_subject": course.get("canonical_subject"),
                    "sections": course.get("sections", []),
                })

    if anomalies:
        print(f"[INTEGRITY WARN] {len(anomalies)} non-thesis allocated course(s) have 0 timetable slots:")
        for a in anomalies[:15]:
            print(f"  - {a['name']} ({a['email']}): {a['course_code']} {a['canonical_subject']} {a['sections']}")
    else:
        print("[INTEGRITY OK] All non-thesis allocated courses have >= 1 scheduled timetable slot.")
    return anomalies


def resolve_active_semester_id(database_url: str, fallback: str = "2026-fall") -> str:
    """Dynamically resolves the currently active semester ID from public.semesters."""
    if is_ci_environment():
        return str(get_active_semester_config()["semester_id"])
    if not HAS_PSYCOPG2 or not database_url:
        return fallback
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM public.semesters
            WHERE is_active = true AND is_published = true AND deleted_at IS NULL
            ORDER BY updated_at DESC LIMIT 1;
            """
        )
        row = cursor.fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception as err:
        print(f"[WARN] Could not resolve active semester from DB ({err}); using fallback '{fallback}'.")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return fallback


def compile_faculty_schedules(
    allocations: List[Dict[str, Any]],
    faculty_roster: List[Dict[str, Any]],
    theory_db: str = THEORY_DB_PATH,
    lab_db: str = LAB_DB_PATH,
    semester_id: str = "2026-fall",
    audit_csv_path: Optional[str] = None,
    audit_json_path: Optional[str] = None,
    return_audit: bool = False,
    return_csv: bool = False,
) -> Union[
    List[Dict[str, Any]],
    Tuple[List[Dict[str, Any]], Dict[str, Any]],
    Tuple[List[Dict[str, Any]], Dict[str, Any], str],
]:
    """
    Joins allocations with SQLite timetable databases and compiles weekly schedule JSON.
    Tracks discrepancies and outputs a comprehensive Reconciliation Audit Report.
    """
    faculty_allocations: Dict[str, Dict[str, Any]] = {}
    unmatched_instructors: Set[str] = set()
    auditor = ReconciliationAuditor(semester_id=semester_id)

    for alloc in allocations:
        instr_name = alloc["raw_instructor"]
        sec = alloc.get("timetable_section", "")
        disc = sec.split("-")[0] if "-" in sec else ""
        if not disc:
            raw_s = alloc.get("raw_section", "").upper()
            if raw_s.startswith("BCS"):
                disc = "CS"
            elif raw_s.startswith("BSE"):
                disc = "SE"
            elif raw_s.startswith("BCY"):
                disc = "CY"
            elif raw_s.startswith("BDS"):
                disc = "DS"
            elif raw_s.startswith("BAI"):
                disc = "AI"

        raw_disc = alloc.get("raw_section", "").split("-")[0] if "-" in alloc.get("raw_section", "") else disc
        match = find_faculty_match(
            instr_name,
            faculty_roster,
            threshold=0.92,
            discipline=raw_disc or disc,
            is_lab=alloc.get("is_lab", False),
            department=alloc.get("sheet", ""),
            course_title=alloc.get("course_title", "")
        )
        
        if not match:
            unmatched_instructors.add(instr_name)
            # Create synthetic fallback record for visiting/external instructors
            clean_name_key = instr_name.lower().strip()
            canonical_name = CANONICAL_FALLBACK_NAMES.get(clean_name_key, instr_name)
            clean_handle = re.sub(r'[^a-z0-9]', '.', normalize_person_name(canonical_name)[0])
            match = {
                "name": canonical_name,
                "email": f"{clean_handle}@nu.edu.pk",
                "dept": alloc["sheet"],
                "desig": "Instructor",
                "office": ""
            }

        if match and match.get("name"):
            match["name"] = CANONICAL_FALLBACK_NAMES.get(match["name"].lower().strip(), match["name"])

        email = match["email"].lower().strip()
        if email not in faculty_allocations:
            faculty_allocations[email] = {
                "faculty_info": match,
                "allocations": []
            }
        faculty_allocations[email]["allocations"].append(alloc)

    if unmatched_instructors:
        auditor.record_unmatched_instructors(unmatched_instructors)
        print(f"[INFO] Generated synthetic accounts for {len(unmatched_instructors)} visiting/external faculty:")
        for u in sorted(unmatched_instructors):
            print(f"  - {u}")

    print(f"Matched allocations to {len(faculty_allocations)} faculty members.")

    conn_theory = sqlite3.connect(theory_db)
    conn_theory.row_factory = sqlite3.Row
    cur_theory = conn_theory.cursor()

    conn_lab = sqlite3.connect(lab_db)
    conn_lab.row_factory = sqlite3.Row
    cur_lab = conn_lab.cursor()

    compiled_records = []
    try:
        for email, data in faculty_allocations.items():
            fac_info = data["faculty_info"]
            allocs = data["allocations"]

            weekly_schedule = {day: [] for day in DAYS_OF_WEEK}
            unique_courses_map = {}
            total_slots = 0
            total_credit_hours = 0.0

            for alloc in allocs:
                c_code = alloc.get("course_code") or ""
                c_title = alloc.get("course_title") or ""
                chs = alloc.get("credit_hours") or 0.0
                b_name = alloc.get("batch") or ""
                sec_name = str(alloc.get("timetable_section") or "").strip()
                canonical_subj = str(alloc.get("canonical_subject") or "").strip()
                is_lab = bool(alloc.get("is_lab", False))

                c_key = f"{c_code}_{canonical_subj}"
                if c_key not in unique_courses_map:
                    unique_courses_map[c_key] = {
                        "course_code": c_code,
                        "course_name": c_title,
                        "canonical_subject": canonical_subj,
                        "credit_hours": chs,
                        "is_lab": is_lab,
                        "sections": set(),
                        "allocations": set(),
                    }
                    total_credit_hours += chs
                if sec_name:
                    unique_courses_map[c_key]["sections"].add(sec_name)
                unique_courses_map[c_key]["allocations"].add((b_name, sec_name))

                rows, final_is_lab = _query_timetable_slots(
                    cur_theory, cur_lab, b_name, sec_name, canonical_subj, is_lab
                )

                if rows:
                    auditor.record_allocation_matched(alloc, fac_info, email, rows, final_is_lab)
                    for row in rows:
                        auditor.record_claimed_slot(final_is_lab, row["ID"])
                else:
                    auditor.record_allocation_unmatched(alloc, fac_info, email, cur_theory, cur_lab)

                for row in rows:
                    total_slots += _merge_slot_into_weekly_schedule(
                        weekly_schedule,
                        row,
                        c_code,
                        c_title,
                        sec_name,
                        b_name,
                        final_is_lab,
                        semester_id=semester_id,
                    )

            for day in DAYS_OF_WEEK:
                weekly_schedule[day].sort(key=lambda s: _parse_time_minutes(s["start_time"]))

            courses_summary = []
            for c in unique_courses_map.values():
                courses_summary.append({
                    "course_code": c["course_code"],
                    "course_name": c["course_name"],
                    "canonical_subject": c["canonical_subject"],
                    "credit_hours": c["credit_hours"],
                    "is_lab": c["is_lab"],
                    "sections": sorted(list(c["sections"])),
                    "allocations": [
                        {"batch": b, "section": s}
                        for b, s in sorted(c["allocations"])
                    ],
                })
            courses_summary.sort(key=lambda x: x["course_code"])

            hash_digest = _compute_schedule_hash(weekly_schedule, courses_summary)

            compiled_records.append({
                "email": email,
                "semester_id": semester_id,
                "name": fac_info.get("name", ""),
                "designation": fac_info.get("desig", ""),
                "department": fac_info.get("dept", ""),
                "office": fac_info.get("office", ""),
                "schedule": weekly_schedule,
                "courses": courses_summary,
                "total_weekly_slots": total_slots,
                "total_credit_hours": total_credit_hours,
                "schedule_hash": hash_digest
            })

        auditor.finalize(cur_theory, cur_lab, semester_id)

        if audit_csv_path:
            auditor.export_csv(audit_csv_path)
        if audit_json_path:
            auditor.export_json(audit_json_path)

        auditor.print_summary()
        verify_compiled_records_integrity(compiled_records)
    finally:
        conn_theory.close()
        conn_lab.close()

    print(f"Compiled weekly schedules for {len(compiled_records)} faculty members.")
    if return_csv and return_audit:
        return compiled_records, auditor.get_summary_dict(), auditor.to_csv_string()
    if return_audit:
        return compiled_records, auditor.get_summary_dict()
    return compiled_records

# =============================================================================
# 5. ATOMIC UPSERT ENGINE & GOVERNANCE RUNNERS
# =============================================================================

class JobError(RuntimeError):
    """Structured error carrying machine-readable error_code for ingestion_jobs."""
    def __init__(self, error_code: str, message: str):
        super().__init__(f"{error_code}: {message}")
        self.error_code = error_code
        self.message = message


KNOWN_ERROR_PREFIXES = (
    "OAUTH_TOKEN_EXPIRED",
    "SHEET_ACCESS_DENIED",
    "SHEET_STRUCTURE_INVALID",
    "ZIP_BOMB_DETECTED",
    "INVALID_XLSX",
    "DRAFT_FILE_EXPIRED",
    "STORAGE_ERROR",
    "TOCTOU_CONFLICT",
    "EMPTY_ALLOCATIONS",
    "EMPTY_DRAFT",
    "MISSING_PARSED_ALLOCATIONS",
    "JOB_CANCELLED_OR_TIMED_OUT",
    "SNAPSHOT_NOT_FOUND",
    "NOT_A_DRAFT",
    "SEMESTER_UNPUBLISHED",
    "RECONCILE_ABORTED",
)


def _classify_error(exc: BaseException) -> Tuple[str, str]:
    if isinstance(exc, JobError):
        return exc.error_code, exc.message[:1000]
    if isinstance(exc, KeyboardInterrupt):
        return "RUNNER_INTERRUPTED", "Runner execution interrupted."
    if isinstance(exc, zipfile.BadZipFile) or "InvalidFileException" in type(exc).__name__:
        return "INVALID_XLSX", (str(exc) or "Invalid .xlsx workbook")[:1000]
    msg = str(exc) or type(exc).__name__
    for prefix in KNOWN_ERROR_PREFIXES:
        if prefix in msg:
            return prefix, msg[:1000]
    return "INTERNAL_ERROR", msg[:1000]


def validate_uuid(raw_id: Optional[str], field_name: str = "id") -> str:
    val = str(raw_id or "").strip()
    if not UUID_PATTERN.fullmatch(val):
        raise ValueError(f"Invalid UUID for {field_name}: {raw_id!r}")
    return val


def serialize_parsed_allocations(allocations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serializes read_course_allocations output verbatim into the exact 11-key JSON schema."""
    return [{k: alloc.get(k) for k in PARSED_ALLOCATION_KEYS} for alloc in allocations]


def compute_aggregate_schedule_sha256(records: List[Dict[str, Any]]) -> str:
    """Computes deterministic SHA-256 across all compiled faculty records."""
    canonical_pairs = [
        [str(r.get("email") or "").lower().strip(), str(r.get("schedule_hash") or "")]
        for r in sorted(records, key=lambda item: str(item.get("email") or "").lower().strip())
    ]
    return hashlib.sha256(
        json.dumps(canonical_pairs, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def validate_xlsx_zip_safety(xlsx_path: str) -> None:
    """Inspects ZIP headers before openpyxl.load_workbook to block zip bombs and invalid files."""
    if not os.path.exists(xlsx_path):
        raise JobError("INVALID_XLSX", f"Workbook file missing at '{xlsx_path}'.")
    try:
        with zipfile.ZipFile(xlsx_path, "r") as zf:
            infos = zf.infolist()
            if len(infos) == 0:
                raise JobError("INVALID_XLSX", "Workbook ZIP archive contains zero entries.")
            if len(infos) > MAX_ZIP_ENTRIES:
                raise JobError(
                    "ZIP_BOMB_DETECTED",
                    f"Workbook archive entry count {len(infos)} exceeds limit of {MAX_ZIP_ENTRIES}.",
                )
            total_uncompressed = 0
            total_compressed = 0
            for info in infos:
                fname = info.filename or ""
                if fname.startswith("/") or ".." in Path(fname).parts:
                    raise JobError("INVALID_XLSX", f"Unsafe archive path entry detected: {fname!r}")
                if info.file_size > MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise JobError(
                        "ZIP_BOMB_DETECTED",
                        f"Archive entry '{fname}' uncompressed size {info.file_size} exceeds 50 MB limit.",
                    )
                total_uncompressed += max(int(info.file_size), 0)
                total_compressed += max(int(info.compress_size), 0)
                if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise JobError(
                        "ZIP_BOMB_DETECTED",
                        f"Total uncompressed workbook size {total_uncompressed} exceeds 50 MB limit.",
                    )
            if total_uncompressed > 1024 * 1024:
                if total_compressed <= 0 or (total_uncompressed / total_compressed) > MAX_ZIP_COMPRESSION_RATIO:
                    raise JobError(
                        "ZIP_BOMB_DETECTED",
                        "Unsafe ZIP compression ratio detected in workbook.",
                    )
    except zipfile.BadZipFile as exc:
        raise JobError("INVALID_XLSX", f"Corrupt or non-ZIP .xlsx workbook: {exc}") from exc


def _encode_storage_path(storage_path: str) -> str:
    return "/".join(quote(seg, safe="") for seg in storage_path.strip("/").split("/"))


def _storage_auth_headers(service_role_key: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    if extra:
        headers.update(extra)
    return headers


def download_storage_object(
    supabase_url: str,
    service_role_key: str,
    storage_path: str,
    dest_path: str,
    bucket: str = "ingestion-uploads",
) -> None:
    base_url = supabase_url.rstrip("/")
    encoded = _encode_storage_path(storage_path)
    url = f"{base_url}/storage/v1/object/{bucket}/{encoded}"
    try:
        resp = requests.get(
            url,
            headers=_storage_auth_headers(service_role_key),
            stream=True,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise JobError("STORAGE_ERROR", f"Storage download failed: {exc}") from exc

    if resp.status_code in (400, 404):
        raise JobError("DRAFT_FILE_EXPIRED", f"Workbook object '{storage_path}' not found in Storage ({resp.status_code}).")
    if not resp.ok:
        raise JobError("STORAGE_ERROR", f"Storage download returned HTTP {resp.status_code}: {resp.text[:300]}")

    total_written = 0
    with open(dest_path, "wb") as out_fh:
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total_written += len(chunk)
            if total_written > MAX_XLSX_DOWNLOAD_BYTES:
                raise JobError("ZIP_BOMB_DETECTED", "Downloaded workbook exceeds maximum allowed size.")
            out_fh.write(chunk)


def copy_storage_object(
    supabase_url: str,
    service_role_key: str,
    source_path: str,
    dest_path: str,
    bucket: str = "ingestion-uploads",
) -> None:
    base_url = supabase_url.rstrip("/")
    url = f"{base_url}/storage/v1/object/copy"
    payload = {
        "bucketId": bucket,
        "sourceKey": source_path,
        "destinationKey": dest_path,
    }
    try:
        resp = requests.post(
            url,
            headers=_storage_auth_headers(service_role_key, {"Content-Type": "application/json"}),
            json=payload,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise JobError("STORAGE_ERROR", f"Storage copy failed: {exc}") from exc

    if not resp.ok:
        raise JobError("STORAGE_ERROR", f"Storage copy returned HTTP {resp.status_code}: {resp.text[:300]}")


def delete_storage_object(
    supabase_url: str,
    service_role_key: str,
    storage_path: Optional[str],
    bucket: str = "ingestion-uploads",
) -> bool:
    if not storage_path or not supabase_url or not service_role_key:
        return False
    base_url = supabase_url.rstrip("/")
    encoded = _encode_storage_path(storage_path)
    url = f"{base_url}/storage/v1/object/{bucket}/{encoded}"
    try:
        resp = requests.delete(
            url,
            headers=_storage_auth_headers(service_role_key),
            timeout=30,
        )
        if resp.ok or resp.status_code == 404:
            return True
        print(f"[WARN] Failed to delete storage object '{storage_path}': HTTP {resp.status_code}")
        return False
    except requests.RequestException as exc:
        print(f"[WARN] Failed to delete storage object '{storage_path}': {exc}")
        return False


def build_sync_callback_body(
    semester_id: str,
    state_version: int,
    status: str,
    error_message: Optional[str] = None,
) -> str:
    norm_status = str(status or "").strip().upper()
    if norm_status not in ("SYNCED", "FAILED"):
        raise ValueError(f"Unsupported callback status: {status!r}")
    payload = {
        "semester_id": str(semester_id),
        "state_version": int(state_version),
        "status": norm_status,
        "error_message": str(error_message)[:500] if error_message else None,
    }
    return json.dumps(payload, separators=(",", ":"))


def sign_sync_callback(
    raw_body: str,
    secret: str,
    timestamp: Optional[int] = None,
) -> Dict[str, str]:
    if not secret:
        raise ValueError("SYNC_CALLBACK_SECRET is required to sign callbacks.")
    ts = str(int(time.time()) if timestamp is None else int(timestamp))
    sig = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.{raw_body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Timestamp": ts,
        "X-Signature": f"sha256={sig}",
        "Content-Type": "application/json",
    }


def send_sync_callback(
    action: str,
    semester_id: str,
    state_version: int,
    status: str,
    error_message: Optional[str] = None,
    portal_callback_url: Optional[str] = None,
    callback_secret: Optional[str] = None,
    sleep_fn=time.sleep,
) -> Dict[str, Any]:
    if action not in ("student_sync_callback", "faculty_sync_callback"):
        raise ValueError(f"Unsupported callback action: {action!r}")

    base_url = (portal_callback_url or os.environ.get("PORTAL_CALLBACK_URL") or "").strip().rstrip("/")
    secret = (callback_secret or os.environ.get("SYNC_CALLBACK_SECRET") or "").strip()
    if not base_url or not secret:
        raise RuntimeError("PORTAL_CALLBACK_URL and SYNC_CALLBACK_SECRET are required for signed callbacks.")

    raw_body = build_sync_callback_body(semester_id, state_version, status, error_message)
    url = f"{base_url}/api/semesters?action={action}"

    last_err: Optional[Exception] = None
    for attempt in range(3):
        headers = sign_sync_callback(raw_body, secret)
        try:
            resp = requests.post(url, data=raw_body.encode("utf-8"), headers=headers, timeout=30)
            if resp.ok:
                try:
                    return resp.json()
                except Exception:
                    return {"ok": True, "status_code": resp.status_code}
            if resp.status_code >= 500 and attempt < 2:
                sleep_fn(1 + attempt)
                continue
            raise RuntimeError(f"Callback '{action}' failed HTTP {resp.status_code}: {resp.text[:300]}")
        except requests.RequestException as exc:
            last_err = exc
            if attempt < 2:
                sleep_fn(1 + attempt)
                continue
            raise RuntimeError(f"Callback '{action}' network error: {exc}") from exc

    raise RuntimeError(f"Callback '{action}' failed: {last_err}")


def upsert_via_psycopg2(
    records: List[Dict[str, Any]],
    database_url: str,
    semester_id: str = "2026-fall",
    audit_summary: Optional[Dict[str, Any]] = None,
    audit_report_csv: Optional[str] = None,
    prune_stale: bool = False,
    expected_state_version: Optional[int] = None,
    require_active: bool = False,
    require_published: bool = False,
    require_auto_enabled: bool = False,
    use_monotonic_version_floor: bool = True,
) -> Dict[str, Any]:
    """
    Atomic batch upsert via PostgreSQL connection pooler (strict Layer 1 schedules only).
    - Acquires `FOR UPDATE` lock on `public.semesters` when governance guards are enabled.
    - Enforces `MAX(version) + 1` floor so returning faculty profiles never drop to version=1.
    - When `prune_stale=True`, deletes Layer 1 profiles absent from the authoritative snapshot.
    - Updates `'LIVE'` snapshot audit metrics without inserting new `ALLOCATION_PUBLISH` rows.
    """
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    stats: Dict[str, Any] = {"aborted": False, "reason": None, "inserted": 0, "updated": 0, "pruned": 0}

    try:
        if (
            expected_state_version is not None
            or require_active
            or require_published
            or require_auto_enabled
        ):
            cursor.execute(
                """
                SELECT status, is_active, is_published, sync_policy, state_version, deleted_at
                FROM public.semesters
                WHERE id = %s
                FOR UPDATE;
                """,
                (semester_id,),
            )
            sem_row = cursor.fetchone()
            abort_reason: Optional[str] = None
            if not sem_row or sem_row.get("deleted_at") is not None:
                abort_reason = "SEMESTER_MISSING_OR_DELETED"
            elif require_active and not sem_row.get("is_active"):
                abort_reason = "SEMESTER_INACTIVE"
            elif require_published and not sem_row.get("is_published"):
                abort_reason = "SEMESTER_UNPUBLISHED"
            elif require_auto_enabled and sem_row.get("sync_policy") != "AUTO_ENABLED":
                abort_reason = f"SYNC_POLICY_{sem_row.get('sync_policy') or 'PAUSED'}"
            elif expected_state_version is not None and int(sem_row.get("state_version") or 0) != int(expected_state_version):
                abort_reason = "TOCTOU_STATE_VERSION_MISMATCH"

            if abort_reason:
                conn.rollback()
                print(f"[ABORT] Semester guard prevented commit for '{semester_id}': {abort_reason}")
                stats["aborted"] = True
                stats["reason"] = abort_reason
                return stats

        next_ver_floor = 1
        if use_monotonic_version_floor:
            cursor.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_ver FROM public.faculty_schedules WHERE semester_id = %s;",
                (semester_id,),
            )
            floor_row = cursor.fetchone()
            if floor_row and floor_row.get("next_ver"):
                next_ver_floor = int(floor_row["next_ver"])

        cursor.execute(
            "SELECT email FROM public.faculty_schedules WHERE semester_id = %s;",
            (semester_id,),
        )
        existing_emails = {
            str(r["email"]).lower().strip() for r in cursor.fetchall()
        }

        incoming_emails: Set[str] = set()
        value_tuples = []

        for rec in records:
            email_norm = str(rec["email"]).lower().strip()
            incoming_emails.add(email_norm)
            raw_sched = rec.get("schedule") or {}
            clean_schedule = {
                day: [s for s in (raw_sched.get(day) or []) if isinstance(s, dict) and not _is_custom_slot(s)]
                for day in DAYS_OF_WEEK
            }
            total_slots = sum(len(clean_schedule[day]) for day in DAYS_OF_WEEK)
            schedule_hash = _compute_schedule_hash(clean_schedule, rec["courses"])

            value_tuples.append((
                email_norm,
                rec.get("semester_id", semester_id),
                rec["name"],
                rec["designation"],
                rec["department"],
                rec["office"],
                json.dumps(clean_schedule),
                json.dumps(rec["courses"]),
                total_slots,
                rec["total_credit_hours"],
                schedule_hash,
                next_ver_floor,
            ))

        upsert_query = """
            INSERT INTO public.faculty_schedules (
                email, semester_id, name, designation, department, office,
                schedule, courses, total_weekly_slots, total_credit_hours,
                schedule_hash, version
            )
            VALUES %s
            ON CONFLICT (email, semester_id) DO UPDATE SET
                name = EXCLUDED.name,
                designation = EXCLUDED.designation,
                department = EXCLUDED.department,
                office = EXCLUDED.office,
                schedule = EXCLUDED.schedule,
                courses = EXCLUDED.courses,
                total_weekly_slots = EXCLUDED.total_weekly_slots,
                total_credit_hours = EXCLUDED.total_credit_hours,
                version = CASE
                    WHEN public.faculty_schedules.schedule_hash = EXCLUDED.schedule_hash THEN public.faculty_schedules.version
                    ELSE GREATEST(public.faculty_schedules.version + 1, EXCLUDED.version)
                END,
                schedule_hash = EXCLUDED.schedule_hash,
                updated_at = CASE
                    WHEN public.faculty_schedules.schedule_hash = EXCLUDED.schedule_hash THEN public.faculty_schedules.updated_at
                    ELSE timezone('utc'::text, now())
                END
            RETURNING (xmax = 0) AS is_insert;
        """

        if value_tuples:
            returned = execute_values(cursor, upsert_query, value_tuples, page_size=100, fetch=True)
            for row in returned:
                if row and row["is_insert"]:
                    stats["inserted"] += 1
                else:
                    stats["updated"] += 1

        if prune_stale:
            for existing_email in existing_emails:
                if existing_email in incoming_emails:
                    continue
                cursor.execute(
                    "DELETE FROM public.faculty_schedules WHERE lower(trim(email)) = %s AND semester_id = %s;",
                    (existing_email, semester_id),
                )
                stats["pruned"] += cursor.rowcount or 1

        aggregate_sha256 = compute_aggregate_schedule_sha256(records)
        if audit_summary is not None or audit_report_csv is not None:
            cursor.execute(
                """
                UPDATE public.semesters
                SET audit_summary = COALESCE(%s, audit_summary),
                    audit_report = COALESCE(%s, audit_report),
                    updated_at = timezone('utc'::text, now())
                WHERE id = %s;
                """,
                (
                    json.dumps(audit_summary) if audit_summary is not None else None,
                    audit_report_csv,
                    semester_id,
                ),
            )
            cursor.execute(
                """
                UPDATE public.semester_snapshots
                SET audit_summary = COALESCE(%s, audit_summary),
                    audit_report_csv = COALESCE(%s, audit_report_csv),
                    faculty_count = %s,
                    schedule_sha256 = %s
                WHERE semester_id = %s
                  AND snapshot_kind = 'ALLOCATION_PUBLISH'
                  AND status = 'LIVE';
                """,
                (
                    json.dumps(audit_summary) if audit_summary is not None else None,
                    audit_report_csv,
                    len(records),
                    aggregate_sha256,
                    semester_id,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE public.semester_snapshots
                SET faculty_count = %s,
                    schedule_sha256 = %s
                WHERE semester_id = %s
                  AND snapshot_kind = 'ALLOCATION_PUBLISH'
                  AND status = 'LIVE';
                """,
                (len(records), aggregate_sha256, semester_id),
            )

        conn.commit()
        print("\n[SUCCESS] Supabase Synchronization Complete:")
        print(f"  - New Profiles Inserted: {stats['inserted']}")
        print(f"  - Profiles Upserted: {stats['updated']}")
        if prune_stale:
            print(f"  - Stale Duplicate Profiles Pruned: {stats['pruned']}")
        return stats
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Failed to upsert to Supabase: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# 6. CONTINUOUS SYNC FROM DATABASE & GOVERNANCE WORKERS
# =============================================================================

def reconcile_existing_db_rows(
    rows: List[Dict[str, Any]],
    cur_theory: sqlite3.Cursor,
    cur_lab: sqlite3.Cursor,
    semester_id: str = "2026-fall",
    year: int = 2026,
    season: str = "fall",
) -> List[Dict[str, Any]]:
    """
    Pure Layer 1 reconciliation engine for continuous synchronization when the Excel
    allocation workbook is absent. Treats `row["courses"]` as the primary authoritative
    allocation source and produces strictly official Layer 1 schedules.
    """
    updated_records = []
    season_lower = (season or "fall").lower().strip()

    for row in rows:
        email = str(row["email"]).lower().strip()
        existing_schedule = row.get("schedule") or {}
        existing_courses = row.get("courses") or []
        if isinstance(existing_courses, str):
            existing_courses = json.loads(existing_courses)

        # Build batch lookup from existing official schedule slots only
        existing_batch_lookup: Dict[Tuple[str, str, bool], str] = {}
        fallback_schedule_classes: Dict[Tuple[str, str, str, bool], Dict[str, Any]] = {}

        for day in DAYS_OF_WEEK:
            slots = existing_schedule.get(day, []) if isinstance(existing_schedule, dict) else []
            if not isinstance(slots, list):
                continue
            for s in slots:
                if not isinstance(s, dict) or _is_custom_slot(s):
                    continue
                s_batch = str(s.get("batch") or "").strip()
                s_sec = str(s.get("section") or "").strip()
                s_subj = str(s.get("subject") or "").strip()
                s_code = str(s.get("course_code") or "").strip()
                s_name = str(s.get("course_name") or "").strip()
                s_lab = bool(s.get("is_lab", False))

                if s_batch:
                    if s_code:
                        existing_batch_lookup[(s_code, s_sec, s_lab)] = s_batch
                    if s_subj:
                        existing_batch_lookup[(s_subj.lower(), s_sec, s_lab)] = s_batch

                if s_subj:
                    fkey = (s_batch, s_sec, s_subj, s_lab)
                    if fkey not in fallback_schedule_classes:
                        fallback_schedule_classes[fkey] = {
                            "batch": s_batch,
                            "section": s_sec,
                            "subject": s_subj,
                            "is_lab": s_lab,
                            "course_code": s_code,
                            "course_name": s_name,
                        }

        # 1. Primary source: authoritative `courses` manifest
        assigned_classes: Dict[Tuple[str, str, str, bool], Dict[str, Any]] = {}
        covered_course_codes: Set[Tuple[str, bool]] = set()
        covered_subjects: Set[Tuple[str, bool]] = set()
        upgraded_courses = []

        for c in existing_courses:
            if not isinstance(c, dict):
                continue
            c_code = str(c.get("course_code") or "").strip()
            c_title = str(c.get("course_name") or "").strip()
            canonical_subj = str(c.get("canonical_subject") or "").strip()
            if not canonical_subj and c_title:
                canonical_subj = resolve_canonical_subject(c_title, c_code, bool(c.get("is_lab", False)))
            is_lab = bool(c.get("is_lab", False))

            if c_code:
                covered_course_codes.add((c_code, is_lab))
            if canonical_subj:
                covered_subjects.add((canonical_subj.lower(), is_lab))

            stored_allocs = c.get("allocations") or []
            alloc_pairs: List[Tuple[str, str]] = []
            if isinstance(stored_allocs, list) and stored_allocs:
                for a in stored_allocs:
                    if isinstance(a, dict):
                        alloc_pairs.append((str(a.get("batch") or "").strip(), str(a.get("section") or "").strip()))
            else:
                secs = c.get("sections") or [""]
                if not secs:
                    secs = [""]
                for sec_name in secs:
                    sec_clean = str(sec_name or "").strip()
                    inferred_batch = (
                        existing_batch_lookup.get((c_code, sec_clean, is_lab))
                        or existing_batch_lookup.get((canonical_subj.lower(), sec_clean, is_lab))
                        or ""
                    )
                    if not inferred_batch and sec_clean:
                        translated = translate_section_code(sec_clean, year=year, season=season_lower)
                        if translated.get("batch"):
                            inferred_batch = translated["batch"]
                            sec_clean = translated.get("timetable_section", sec_clean)
                    alloc_pairs.append((inferred_batch, sec_clean))

            discovered_allocs: Set[Tuple[str, str]] = set()
            for b_name, sec_name in alloc_pairs:
                key = (b_name, sec_name, canonical_subj, is_lab)
                if canonical_subj and key not in assigned_classes:
                    assigned_classes[key] = {
                        "batch": b_name,
                        "section": sec_name,
                        "subject": canonical_subj,
                        "is_lab": is_lab,
                        "course_code": c_code,
                        "course_name": c_title,
                        "source_course_ref": discovered_allocs,
                    }
                discovered_allocs.add((b_name, sec_name))

            upgraded_c = dict(c)
            upgraded_c["_discovered_allocs"] = discovered_allocs
            upgraded_courses.append(upgraded_c)

        # 2. Secondary fallback: any official schedule entries from courses not listed in `courses`
        for fkey, cls_info in fallback_schedule_classes.items():
            fc_code = cls_info["course_code"]
            fc_subj = cls_info["subject"].lower()
            fc_lab = cls_info["is_lab"]
            already_covered = (
                (fc_code and (fc_code, fc_lab) in covered_course_codes)
                or (fc_subj, fc_lab) in covered_subjects
                or any(
                    (cs and (cs in fc_subj or fc_subj in cs))
                    for cs, clab in covered_subjects
                    if clab == fc_lab
                )
            )
            if not already_covered and fkey not in assigned_classes:
                assigned_classes[fkey] = cls_info

        weekly_schedule = {day: [] for day in DAYS_OF_WEEK}
        total_slots = 0

        for cls_info in assigned_classes.values():
            b_name = cls_info.get("batch") or ""
            sec_name = str(cls_info.get("section") or "").strip()
            canonical_subj = str(cls_info.get("subject") or "").strip()
            is_lab = bool(cls_info.get("is_lab", False))
            c_code = cls_info.get("course_code") or ""
            c_title = cls_info.get("course_name") or ""

            matches, final_is_lab = _query_timetable_slots(
                cur_theory, cur_lab, b_name, sec_name, canonical_subj, is_lab
            )

            ref_set = cls_info.get("source_course_ref")
            if isinstance(ref_set, set) and matches and not b_name:
                matched_batches = {str(m["BATCH"] or "").strip() for m in matches if m["BATCH"]}
                if len(matched_batches) == 1:
                    ref_set.discard(("", sec_name))
                    ref_set.add((next(iter(matched_batches)), sec_name))

            for m in matches:
                total_slots += _merge_slot_into_weekly_schedule(
                    weekly_schedule,
                    m,
                    c_code,
                    c_title,
                    sec_name,
                    b_name,
                    final_is_lab,
                    semester_id=semester_id,
                )

        # Normalize upgraded courses manifest with self-healed allocations
        final_courses = []
        for c in upgraded_courses:
            discovered = c.pop("_discovered_allocs", set())
            if discovered:
                c["allocations"] = [
                    {"batch": b, "section": s} for b, s in sorted(discovered)
                ]
            final_courses.append(c)

        for day in DAYS_OF_WEEK:
            weekly_schedule[day].sort(key=lambda s: _parse_time_minutes(str(s.get("start_time") or "00:00")))

        total_slots = sum(len(weekly_schedule.get(d, [])) for d in DAYS_OF_WEEK)
        new_hash = _compute_schedule_hash(weekly_schedule, final_courses)

        updated_records.append({
            "email": email,
            "semester_id": row.get("semester_id", semester_id),
            "name": row["name"],
            "designation": row["designation"],
            "department": row["department"],
            "office": row["office"],
            "schedule": weekly_schedule,
            "courses": final_courses,
            "total_weekly_slots": total_slots,
            "total_credit_hours": row.get("total_credit_hours", 0),
            "schedule_hash": new_hash,
        })

    verify_compiled_records_integrity(updated_records)
    return updated_records


def sync_from_existing_database(
    db_url: str,
    theory_db: str = THEORY_DB_PATH,
    lab_db: str = LAB_DB_PATH,
    dry_run: bool = False,
    semester_id: str = "auto",
) -> Dict[str, Any]:
    """
    Continuous synchronization mode (`--mode sync`).
    Queries `academic_year, season, state_version` from `public.semesters`, reconciles
    Layer 1 faculty schedules using local SQLite databases, and commits via `FOR UPDATE`
    parity checks on `is_active`, `is_published`, `deleted_at IS NULL`, `sync_policy == 'AUTO_ENABLED'`,
    and `state_version`.
    """
    if not HAS_PSYCOPG2:
        raise RuntimeError("psycopg2 is required for database sync. Run: pip install psycopg2-binary")

    if semester_id == "auto" or not semester_id:
        cfg = get_active_semester_config()
        resolved_sem_id = str(cfg["semester_id"])
    else:
        resolved_sem_id = semester_id

    conn_db = psycopg2.connect(db_url)
    cur_db = conn_db.cursor(cursor_factory=RealDictCursor)
    try:
        cur_db.execute(
            """
            SELECT id, academic_year, season, sync_policy, state_version, is_active, is_published, deleted_at
            FROM public.semesters
            WHERE id = %s;
            """,
            (resolved_sem_id,),
        )
        sem_row = cur_db.fetchone()
        if not sem_row or sem_row.get("deleted_at") is not None:
            print(f"[ABORT] Semester '{resolved_sem_id}' not found or soft-deleted.")
            return {"aborted": True, "reason": "SEMESTER_MISSING_OR_DELETED"}
        if not sem_row.get("is_active") or not sem_row.get("is_published"):
            print(f"[ABORT] Semester '{resolved_sem_id}' is inactive or unpublished.")
            return {"aborted": True, "reason": "SEMESTER_INACTIVE_OR_UNPUBLISHED"}
        if sem_row.get("sync_policy") != "AUTO_ENABLED":
            print(f"[SKIP] Auto sync is paused for '{resolved_sem_id}' (sync_policy={sem_row.get('sync_policy')}).")
            return {"aborted": True, "reason": f"SYNC_POLICY_{sem_row.get('sync_policy')}"}

        sem_year = int(sem_row.get("academic_year") or 2026)
        sem_season = str(sem_row.get("season") or "fall").lower()
        expected_state_version = int(sem_row.get("state_version") or 1)

        cur_db.execute(
            """
            SELECT email, semester_id, name, designation, department, office,
                   schedule, courses, schedule_hash, version, total_credit_hours
            FROM public.faculty_schedules
            WHERE semester_id = %s;
            """,
            (resolved_sem_id,),
        )
        rows = cur_db.fetchall()
    finally:
        cur_db.close()
        conn_db.close()

    if not rows:
        print(f"[WARN] No existing faculty profiles found in Supabase for semester '{resolved_sem_id}'.")
        return {"aborted": False, "inserted": 0, "updated": 0, "pruned": 0}

    print(
        f"Loaded {len(rows)} faculty profiles from Supabase for semester '{resolved_sem_id}' "
        f"(year={sem_year}, season={sem_season}, state_version={expected_state_version})."
    )

    conn_theory = sqlite3.connect(theory_db)
    conn_theory.row_factory = sqlite3.Row
    cur_theory = conn_theory.cursor()

    conn_lab = sqlite3.connect(lab_db)
    conn_lab.row_factory = sqlite3.Row
    cur_lab = conn_lab.cursor()
    try:
        updated_records = reconcile_existing_db_rows(
            rows,
            cur_theory,
            cur_lab,
            semester_id=resolved_sem_id,
            year=sem_year,
            season=sem_season,
        )
    finally:
        conn_theory.close()
        conn_lab.close()

    if dry_run:
        print(f"\n[DRY RUN] Successfully processed {len(updated_records)} faculty profiles for '{resolved_sem_id}'.")
        return {"aborted": False, "dry_run": True, "count": len(updated_records)}

    return upsert_via_psycopg2(
        updated_records,
        db_url,
        semester_id=resolved_sem_id,
        prune_stale=False,
        expected_state_version=expected_state_version,
        require_active=True,
        require_published=True,
        require_auto_enabled=True,
        use_monotonic_version_floor=True,
    )


def _update_job_progress(db_url: str, job_id: str, progress_step: str) -> None:
    """Best-effort heartbeat & progress update on a RUNNING ingestion job."""
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE public.ingestion_jobs
            SET progress_step = %s,
                heartbeat_at = timezone('utc'::text, now())
            WHERE id = %s AND status = 'RUNNING';
            """,
            (progress_step, job_id),
        )
    except Exception as exc:
        print(f"[WARN] Failed to update job progress ({progress_step}): {exc}")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def _mark_job_failed(db_url: str, job_id: str, error_code: str, error_message: str) -> None:
    """Marks a claimed RUNNING ingestion job FAILED so jobs never stick in RUNNING."""
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE public.ingestion_jobs
            SET status = 'FAILED',
                error_code = %s,
                error_message = %s,
                completed_at = timezone('utc'::text, now()),
                heartbeat_at = timezone('utc'::text, now())
            WHERE id = %s AND status = 'RUNNING';
            """,
            (error_code[:64], error_message[:1000], job_id),
        )
    except Exception as exc:
        print(f"[ERROR] Failed to mark ingestion job '{job_id}' FAILED: {exc}")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def _claim_ingestion_job(db_url: str, job_id: str) -> Optional[Dict[str, Any]]:
    """Atomically claims a QUEUED ingestion job (`QUEUED` -> `RUNNING`)."""
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            UPDATE public.ingestion_jobs
            SET status = 'RUNNING',
                started_at = timezone('utc'::text, now()),
                heartbeat_at = timezone('utc'::text, now()),
                progress_step = 'CLAIMING_JOB',
                github_run_id = COALESCE(%s, github_run_id)
            WHERE id = %s AND status = 'QUEUED'
            RETURNING *;
            """,
            (os.environ.get("GITHUB_RUN_ID"), job_id),
        )
        claimed = cursor.fetchone()
        conn.commit()
        return dict(claimed) if claimed else None
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def _insert_draft_snapshot_and_rows(
    cursor,
    snapshot_id: str,
    semester_id: str,
    google_sheet_id: str,
    parsed_allocations: List[Dict[str, Any]],
    allocation_storage_path: Optional[str],
    created_by: str,
    records: List[Dict[str, Any]],
    audit_summary: Dict[str, Any],
    csv_text: str,
) -> Tuple[int, List[str]]:
    """Marks prior DRAFT snapshots DISCARDED and inserts the new DRAFT snapshot + rows."""
    cursor.execute(
        """
        SELECT id, allocation_storage_path
        FROM public.semester_snapshots
        WHERE semester_id = %s AND status = 'DRAFT'
        FOR UPDATE;
        """,
        (semester_id,),
    )
    prior_drafts = cursor.fetchall()
    old_draft_ids = [str(r["id"]) for r in prior_drafts]
    old_draft_paths = [
        str(r["allocation_storage_path"])
        for r in prior_drafts
        if r.get("allocation_storage_path")
    ]

    if old_draft_ids:
        cursor.execute(
            "DELETE FROM public.semester_snapshot_rows WHERE snapshot_id = ANY(%s::uuid[]);",
            (old_draft_ids,),
        )
        cursor.execute(
            "UPDATE public.semester_snapshots SET status = 'DISCARDED' WHERE id = ANY(%s::uuid[]);",
            (old_draft_ids,),
        )

    cursor.execute(
        "SELECT COALESCE(MAX(revision_number), 0) + 1 AS next_rev FROM public.semester_snapshots WHERE semester_id = %s;",
        (semester_id,),
    )
    rev_row = cursor.fetchone()
    revision_number = int(rev_row["next_rev"]) if rev_row and rev_row.get("next_rev") else 1

    schedule_sha256 = compute_aggregate_schedule_sha256(records)

    cursor.execute(
        """
        INSERT INTO public.semester_snapshots (
            id, semester_id, revision_number, snapshot_kind, status,
            google_sheet_id, parsed_allocations, allocation_storage_path,
            created_by, schedule_sha256, faculty_count,
            audit_summary, audit_report_csv
        ) VALUES (%s, %s, %s, 'ALLOCATION_PUBLISH', 'DRAFT', %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s);
        """,
        (
            snapshot_id,
            semester_id,
            revision_number,
            google_sheet_id,
            json.dumps(parsed_allocations),
            allocation_storage_path,
            created_by,
            schedule_sha256,
            len(records),
            json.dumps(audit_summary),
            csv_text,
        ),
    )

    row_tuples = [
        (
            snapshot_id,
            str(rec["email"]).lower().strip(),
            rec.get("name", ""),
            rec.get("designation", ""),
            rec.get("department", ""),
            rec.get("office", ""),
            json.dumps(rec.get("schedule") or {}),
            json.dumps(rec.get("courses") or []),
            int(rec.get("total_weekly_slots") or 0),
            rec.get("total_credit_hours") or 0,
            str(rec.get("schedule_hash") or ""),
        )
        for rec in records
    ]
    if row_tuples:
        execute_values(
            cursor,
            """
            INSERT INTO public.semester_snapshot_rows (
                snapshot_id, email, name, designation, department, office,
                schedule, courses, total_weekly_slots, total_credit_hours, schedule_hash
            ) VALUES %s;
            """,
            row_tuples,
            page_size=100,
        )

    return revision_number, old_draft_paths


def run_draft_job(
    job_id: str,
    db_url: str,
    supabase_url: str,
    service_role_key: str,
) -> Dict[str, Any]:
    """
    Isolated draft ingestion runner (`--mode draft --job-id <uuid>`).
    Never mutates live `faculty_schedules`, repo `*.db`, or `frontend/data/*.bin`.
    """
    if not HAS_PSYCOPG2:
        raise RuntimeError("psycopg2 is required for draft ingestion.")
    if not supabase_url or not service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for draft ingestion.")

    job_id = validate_uuid(job_id, "job_id")
    job = _claim_ingestion_job(db_url, job_id)
    if not job:
        print(f"[INFO] Ingestion job '{job_id}' is not in QUEUED state; exiting cleanly.")
        return {"claimed": False, "job_id": job_id}

    copied_snapshot_path: Optional[str] = None
    try:
        semester_id = str(job["semester_id"])
        src_storage_path = str(job.get("allocation_storage_path") or "").strip()
        if not src_storage_path:
            raise JobError("DRAFT_FILE_EXPIRED", "Job record has empty allocation_storage_path.")
        try:
            google_sheet_id = validate_spreadsheet_id(job.get("google_sheet_id") or "")
        except ValueError as exc:
            raise JobError("SHEET_STRUCTURE_INVALID", str(exc)) from exc

        conn_meta = psycopg2.connect(db_url)
        cur_meta = conn_meta.cursor(cursor_factory=RealDictCursor)
        try:
            cur_meta.execute(
                "SELECT id, academic_year, season FROM public.semesters WHERE id = %s;",
                (semester_id,),
            )
            sem_meta = cur_meta.fetchone()
        finally:
            cur_meta.close()
            conn_meta.close()

        if not sem_meta:
            raise JobError("INTERNAL_ERROR", f"Target semester '{semester_id}' not found.")
        sem_year = int(sem_meta.get("academic_year") or 2026)
        sem_season = str(sem_meta.get("season") or "fall").lower()

        from rebuild_db import build_sqlite_from_google_sheet

        with tempfile.TemporaryDirectory(prefix=f"draft_{job_id}_", dir="/tmp") as tmpdir:
            tmp_xlsx = os.path.join(tmpdir, "allocation.xlsx")
            tmp_theory_db = os.path.join(tmpdir, f"draft_theory_{job_id}.db")
            tmp_lab_db = os.path.join(tmpdir, f"draft_lab_{job_id}.db")
            tmp_csv = os.path.join(tmpdir, f"draft_audit_{job_id}.csv")
            tmp_json = os.path.join(tmpdir, f"draft_audit_{job_id}.json")

            _update_job_progress(db_url, job_id, "DOWNLOADING_WORKBOOK")
            download_storage_object(supabase_url, service_role_key, src_storage_path, tmp_xlsx)
            validate_xlsx_zip_safety(tmp_xlsx)

            _update_job_progress(db_url, job_id, "PARSING_ALLOCATIONS")
            allocations = read_course_allocations(excel_path=tmp_xlsx, year=sem_year, season=sem_season)
            if not allocations:
                raise JobError("EMPTY_ALLOCATIONS", "Course Allocation workbook yielded zero valid rows.")
            parsed_allocations = serialize_parsed_allocations(allocations)

            _update_job_progress(db_url, job_id, "READING_GOOGLE_SHEET")
            build_sqlite_from_google_sheet(
                google_sheet_id,
                course_db=tmp_theory_db,
                lab_db=tmp_lab_db,
            )

            _update_job_progress(db_url, job_id, "COMPILING_SCHEDULES")
            faculty_roster = decode_faculty_bin(FACULTY_BIN_PATH)
            records, audit_summary, csv_text = compile_faculty_schedules(
                parsed_allocations,
                faculty_roster,
                theory_db=tmp_theory_db,
                lab_db=tmp_lab_db,
                semester_id=semester_id,
                audit_csv_path=tmp_csv,
                audit_json_path=tmp_json,
                return_audit=True,
                return_csv=True,
            )
            if not records:
                raise JobError("EMPTY_DRAFT", "Compiled zero faculty schedules for draft snapshot.")

        _update_job_progress(db_url, job_id, "PROMOTING_SNAPSHOT")
        snapshot_id = str(uuid.uuid4())
        dst_storage_path = f"snapshots/{semester_id}/{snapshot_id}.xlsx"
        copy_storage_object(supabase_url, service_role_key, src_storage_path, dst_storage_path)
        copied_snapshot_path = dst_storage_path

        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        old_draft_paths: List[str] = []
        try:
            cursor.execute("SELECT id FROM public.semesters WHERE id = %s FOR UPDATE;", (semester_id,))
            cursor.execute("SELECT * FROM public.ingestion_jobs WHERE id = %s FOR UPDATE;", (job_id,))
            locked_job = cursor.fetchone()
            if not locked_job or locked_job.get("status") != "RUNNING":
                conn.rollback()
                status_now = locked_job.get("status") if locked_job else "MISSING"
                raise JobError(
                    "JOB_CANCELLED_OR_TIMED_OUT",
                    f"Job '{job_id}' transitioned to '{status_now}' mid-run; aborting draft commit.",
                )

            revision_number, old_draft_paths = _insert_draft_snapshot_and_rows(
                cursor=cursor,
                snapshot_id=snapshot_id,
                semester_id=semester_id,
                google_sheet_id=google_sheet_id,
                parsed_allocations=parsed_allocations,
                allocation_storage_path=dst_storage_path,
                created_by=str(job.get("requested_by") or "system"),
                records=records,
                audit_summary=audit_summary,
                csv_text=csv_text,
            )

            cursor.execute(
                """
                UPDATE public.semesters
                SET draft_snapshot_id = %s,
                    state_version = state_version + 1,
                    updated_at = timezone('utc'::text, now())
                WHERE id = %s;
                """,
                (snapshot_id, semester_id),
            )
            cursor.execute(
                """
                UPDATE public.ingestion_jobs
                SET status = 'READY',
                    progress_step = 'READY',
                    produced_snapshot_id = %s,
                    completed_at = timezone('utc'::text, now()),
                    heartbeat_at = timezone('utc'::text, now())
                WHERE id = %s AND status = 'RUNNING';
                """,
                (snapshot_id, job_id),
            )
            conn.commit()
            copied_snapshot_path = None
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

        # Post-commit storage cleanup: delete uploads/... and superseded discarded draft objects
        delete_storage_object(supabase_url, service_role_key, src_storage_path)
        for old_path in old_draft_paths:
            if old_path and old_path != dst_storage_path:
                delete_storage_object(supabase_url, service_role_key, old_path)

        print(
            f"[SUCCESS] Draft job '{job_id}' completed -> snapshot '{snapshot_id}' "
            f"(rev={revision_number}, faculty={len(records)})."
        )
        return {
            "claimed": True,
            "job_id": job_id,
            "snapshot_id": snapshot_id,
            "revision_number": revision_number,
            "faculty_count": len(records),
        }
    except BaseException as exc:
        if copied_snapshot_path:
            delete_storage_object(supabase_url, service_role_key, copied_snapshot_path)
        err_code, err_msg = _classify_error(exc)
        _mark_job_failed(db_url, job_id, err_code, err_msg)
        raise


def run_refresh_draft_job(
    job_id: str,
    db_url: str,
    supabase_url: str,
    service_role_key: str,
) -> Dict[str, Any]:
    """
    Non-destructive draft sheet refresh (`--mode refresh-draft --job-id <uuid>`).
    Re-compiles the active DRAFT snapshot's allocations against `job.google_sheet_id`.
    If anything fails, leaves the previous DRAFT snapshot 100% intact and publishable.
    """
    if not HAS_PSYCOPG2:
        raise RuntimeError("psycopg2 is required for refresh-draft.")
    if not supabase_url or not service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for refresh-draft.")

    job_id = validate_uuid(job_id, "job_id")
    job = _claim_ingestion_job(db_url, job_id)
    if not job:
        print(f"[INFO] Refresh job '{job_id}' is not in QUEUED state; exiting cleanly.")
        return {"claimed": False, "job_id": job_id}

    copied_snapshot_path: Optional[str] = None
    try:
        semester_id = str(job["semester_id"])
        source_snapshot_id = str(job.get("source_snapshot_id") or "").strip()
        if not source_snapshot_id:
            raise JobError("MISSING_PARSED_ALLOCATIONS", "Refresh job lacks source_snapshot_id.")
        try:
            google_sheet_id = validate_spreadsheet_id(job.get("google_sheet_id") or "")
        except ValueError as exc:
            raise JobError("SHEET_STRUCTURE_INVALID", str(exc)) from exc

        conn_meta = psycopg2.connect(db_url)
        cur_meta = conn_meta.cursor(cursor_factory=RealDictCursor)
        try:
            cur_meta.execute(
                """
                SELECT ss.id, ss.status, ss.parsed_allocations, ss.allocation_storage_path,
                       sem.academic_year, sem.season
                FROM public.semester_snapshots ss
                JOIN public.semesters sem ON sem.id = ss.semester_id
                WHERE ss.id = %s AND ss.semester_id = %s;
                """,
                (source_snapshot_id, semester_id),
            )
            snap_meta = cur_meta.fetchone()
        finally:
            cur_meta.close()
            conn_meta.close()

        if not snap_meta or snap_meta.get("status") != "DRAFT":
            raise JobError("NOT_A_DRAFT", f"Source snapshot '{source_snapshot_id}' is not an active DRAFT.")

        sem_year = int(snap_meta.get("academic_year") or 2026)
        sem_season = str(snap_meta.get("season") or "fall").lower()
        src_storage_path = snap_meta.get("allocation_storage_path")
        raw_parsed = snap_meta.get("parsed_allocations")
        if isinstance(raw_parsed, str):
            raw_parsed = json.loads(raw_parsed)

        from rebuild_db import build_sqlite_from_google_sheet

        with tempfile.TemporaryDirectory(prefix=f"refresh_{job_id}_", dir="/tmp") as tmpdir:
            tmp_xlsx = os.path.join(tmpdir, "source_allocation.xlsx")
            tmp_theory_db = os.path.join(tmpdir, f"refresh_theory_{job_id}.db")
            tmp_lab_db = os.path.join(tmpdir, f"refresh_lab_{job_id}.db")
            tmp_csv = os.path.join(tmpdir, f"refresh_audit_{job_id}.csv")
            tmp_json = os.path.join(tmpdir, f"refresh_audit_{job_id}.json")

            if isinstance(raw_parsed, list) and len(raw_parsed) > 0:
                parsed_allocations = serialize_parsed_allocations(raw_parsed)
            elif src_storage_path:
                _update_job_progress(db_url, job_id, "DOWNLOADING_WORKBOOK")
                download_storage_object(supabase_url, service_role_key, src_storage_path, tmp_xlsx)
                validate_xlsx_zip_safety(tmp_xlsx)
                allocations = read_course_allocations(excel_path=tmp_xlsx, year=sem_year, season=sem_season)
                if not allocations:
                    raise JobError("EMPTY_ALLOCATIONS", "Source workbook yielded zero valid rows.")
                parsed_allocations = serialize_parsed_allocations(allocations)
            else:
                raise JobError(
                    "MISSING_PARSED_ALLOCATIONS",
                    f"Source draft '{source_snapshot_id}' lacks parsed_allocations and allocation_storage_path.",
                )

            _update_job_progress(db_url, job_id, "READING_GOOGLE_SHEET")
            build_sqlite_from_google_sheet(
                google_sheet_id,
                course_db=tmp_theory_db,
                lab_db=tmp_lab_db,
            )

            _update_job_progress(db_url, job_id, "COMPILING_SCHEDULES")
            faculty_roster = decode_faculty_bin(FACULTY_BIN_PATH)
            records, audit_summary, csv_text = compile_faculty_schedules(
                parsed_allocations,
                faculty_roster,
                theory_db=tmp_theory_db,
                lab_db=tmp_lab_db,
                semester_id=semester_id,
                audit_csv_path=tmp_csv,
                audit_json_path=tmp_json,
                return_audit=True,
                return_csv=True,
            )
            if not records:
                raise JobError("EMPTY_DRAFT", "Compiled zero faculty schedules during draft sheet refresh.")

        _update_job_progress(db_url, job_id, "PROMOTING_SNAPSHOT")
        new_snap_id = str(uuid.uuid4())
        new_storage_path: Optional[str] = None
        if src_storage_path:
            new_storage_path = f"snapshots/{semester_id}/{new_snap_id}.xlsx"
            copy_storage_object(supabase_url, service_role_key, src_storage_path, new_storage_path)
            copied_snapshot_path = new_storage_path

        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        old_draft_paths: List[str] = []
        try:
            cursor.execute("SELECT id FROM public.semesters WHERE id = %s FOR UPDATE;", (semester_id,))
            cursor.execute("SELECT * FROM public.ingestion_jobs WHERE id = %s FOR UPDATE;", (job_id,))
            locked_job = cursor.fetchone()
            if not locked_job or locked_job.get("status") != "RUNNING":
                conn.rollback()
                status_now = locked_job.get("status") if locked_job else "MISSING"
                raise JobError(
                    "JOB_CANCELLED_OR_TIMED_OUT",
                    f"Refresh job '{job_id}' transitioned to '{status_now}' mid-run; aborting.",
                )

            cursor.execute(
                "SELECT status FROM public.semester_snapshots WHERE id = %s AND semester_id = %s FOR UPDATE;",
                (source_snapshot_id, semester_id),
            )
            src_locked = cursor.fetchone()
            if not src_locked or src_locked.get("status") != "DRAFT":
                conn.rollback()
                raise JobError(
                    "NOT_A_DRAFT",
                    f"Source draft '{source_snapshot_id}' is no longer DRAFT; aborting refresh.",
                )

            revision_number, old_draft_paths = _insert_draft_snapshot_and_rows(
                cursor=cursor,
                snapshot_id=new_snap_id,
                semester_id=semester_id,
                google_sheet_id=google_sheet_id,
                parsed_allocations=parsed_allocations,
                allocation_storage_path=new_storage_path,
                created_by=str(job.get("requested_by") or "system"),
                records=records,
                audit_summary=audit_summary,
                csv_text=csv_text,
            )

            cursor.execute(
                """
                UPDATE public.semesters
                SET draft_snapshot_id = %s,
                    state_version = state_version + 1,
                    updated_at = timezone('utc'::text, now())
                WHERE id = %s;
                """,
                (new_snap_id, semester_id),
            )
            cursor.execute(
                """
                UPDATE public.ingestion_jobs
                SET status = 'READY',
                    progress_step = 'READY',
                    produced_snapshot_id = %s,
                    completed_at = timezone('utc'::text, now()),
                    heartbeat_at = timezone('utc'::text, now())
                WHERE id = %s AND status = 'RUNNING';
                """,
                (new_snap_id, job_id),
            )
            conn.commit()
            copied_snapshot_path = None
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

        for old_path in old_draft_paths:
            if old_path and old_path != new_storage_path:
                delete_storage_object(supabase_url, service_role_key, old_path)

        print(
            f"[SUCCESS] Refresh job '{job_id}' completed -> snapshot '{new_snap_id}' "
            f"(rev={revision_number}, faculty={len(records)})."
        )
        return {
            "claimed": True,
            "job_id": job_id,
            "snapshot_id": new_snap_id,
            "revision_number": revision_number,
            "faculty_count": len(records),
        }
    except BaseException as exc:
        if copied_snapshot_path:
            delete_storage_object(supabase_url, service_role_key, copied_snapshot_path)
        err_code, err_msg = _classify_error(exc)
        _mark_job_failed(db_url, job_id, err_code, err_msg)
        raise


def run_reconcile_snapshot(
    snapshot_id: str,
    expected_version: int,
    db_url: str,
    supabase_url: Optional[str] = None,
    service_role_key: Optional[str] = None,
    portal_callback_url: Optional[str] = None,
    callback_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Hybrid live-sheet re-reconcile (`--mode reconcile-snapshot --snapshot-id <uuid> --expected-version <int>`).
    Re-compiles a target snapshot's `parsed_allocations` against the semester's current live
    Google Sheet, upserts Layer 1 schedules with `prune_stale=True` and `MAX(version)+1` floor,
    updates LIVE audit metrics without inserting `ALLOCATION_PUBLISH` rows, and sends signed
    HMAC `faculty_sync_callback`.
    """
    if not HAS_PSYCOPG2:
        raise RuntimeError("psycopg2 is required for reconcile-snapshot.")

    snapshot_id = validate_uuid(snapshot_id, "snapshot_id")
    expected_version = int(expected_version)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT ss.id, ss.semester_id, ss.status, ss.google_sheet_id AS snap_sheet_id,
                   ss.parsed_allocations, ss.allocation_storage_path,
                   sem.academic_year, sem.season, sem.google_sheet_id AS sem_sheet_id,
                   sem.state_version, sem.is_published, sem.deleted_at
            FROM public.semester_snapshots ss
            JOIN public.semesters sem ON sem.id = ss.semester_id
            WHERE ss.id = %s;
            """,
            (snapshot_id,),
        )
        snap_row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not snap_row:
        raise JobError("SNAPSHOT_NOT_FOUND", f"Snapshot '{snapshot_id}' not found.")

    semester_id = str(snap_row["semester_id"])
    try:
        if snap_row.get("deleted_at") is not None or not snap_row.get("is_published"):
            raise JobError(
                "SEMESTER_UNPUBLISHED",
                f"Semester '{semester_id}' is unpublished or soft-deleted; cannot reconcile.",
            )

        if int(snap_row.get("state_version") or 0) != expected_version:
            print(
                f"[ABORT] Snapshot reconcile stale: expected state_version={expected_version}, "
                f"found {snap_row.get('state_version')}."
            )
            return {"aborted": True, "reason": "TOCTOU_STATE_VERSION_MISMATCH"}

        raw_sheet = (snap_row.get("sem_sheet_id") or snap_row.get("snap_sheet_id") or "").strip()
        try:
            live_sheet_id = validate_spreadsheet_id(raw_sheet)
        except ValueError as exc:
            raise JobError("SHEET_STRUCTURE_INVALID", str(exc)) from exc

        sem_year = int(snap_row.get("academic_year") or 2026)
        sem_season = str(snap_row.get("season") or "fall").lower()
        raw_parsed = snap_row.get("parsed_allocations")
        if isinstance(raw_parsed, str):
            raw_parsed = json.loads(raw_parsed)
        storage_path = snap_row.get("allocation_storage_path")

        from rebuild_db import build_sqlite_from_google_sheet

        audit_summary: Optional[Dict[str, Any]] = None
        csv_text: Optional[str] = None

        with tempfile.TemporaryDirectory(prefix=f"reconcile_{snapshot_id}_", dir="/tmp") as tmpdir:
            tmp_xlsx = os.path.join(tmpdir, "reconcile_allocation.xlsx")
            tmp_theory_db = os.path.join(tmpdir, f"reconcile_theory_{snapshot_id}.db")
            tmp_lab_db = os.path.join(tmpdir, f"reconcile_lab_{snapshot_id}.db")
            tmp_csv = os.path.join(tmpdir, f"reconcile_audit_{snapshot_id}.csv")
            tmp_json = os.path.join(tmpdir, f"reconcile_audit_{snapshot_id}.json")

            build_sqlite_from_google_sheet(
                live_sheet_id,
                course_db=tmp_theory_db,
                lab_db=tmp_lab_db,
            )

            if isinstance(raw_parsed, list) and len(raw_parsed) > 0:
                allocations = serialize_parsed_allocations(raw_parsed)
                faculty_roster = decode_faculty_bin(FACULTY_BIN_PATH)
                records, audit_summary, csv_text = compile_faculty_schedules(
                    allocations,
                    faculty_roster,
                    theory_db=tmp_theory_db,
                    lab_db=tmp_lab_db,
                    semester_id=semester_id,
                    audit_csv_path=tmp_csv,
                    audit_json_path=tmp_json,
                    return_audit=True,
                    return_csv=True,
                )
            elif storage_path:
                if not supabase_url or not service_role_key:
                    raise JobError(
                        "STORAGE_ERROR",
                        "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required to download snapshot workbook.",
                    )
                download_storage_object(supabase_url, service_role_key, storage_path, tmp_xlsx)
                validate_xlsx_zip_safety(tmp_xlsx)
                allocations = read_course_allocations(excel_path=tmp_xlsx, year=sem_year, season=sem_season)
                faculty_roster = decode_faculty_bin(FACULTY_BIN_PATH)
                records, audit_summary, csv_text = compile_faculty_schedules(
                    allocations,
                    faculty_roster,
                    theory_db=tmp_theory_db,
                    lab_db=tmp_lab_db,
                    semester_id=semester_id,
                    audit_csv_path=tmp_csv,
                    audit_json_path=tmp_json,
                    return_audit=True,
                    return_csv=True,
                )
            else:
                conn_rows = psycopg2.connect(db_url)
                cur_rows = conn_rows.cursor(cursor_factory=RealDictCursor)
                try:
                    cur_rows.execute(
                        """
                        SELECT email, %s AS semester_id, name, designation, department, office,
                               schedule, courses, schedule_hash, total_credit_hours
                        FROM public.semester_snapshot_rows
                        WHERE snapshot_id = %s;
                        """,
                        (semester_id, snapshot_id),
                    )
                    snap_rows = cur_rows.fetchall()
                finally:
                    cur_rows.close()
                    conn_rows.close()

                if not snap_rows:
                    raise JobError(
                        "MISSING_PARSED_ALLOCATIONS",
                        f"Snapshot '{snapshot_id}' has no parsed_allocations, workbook, or snapshot rows.",
                    )

                conn_t = sqlite3.connect(tmp_theory_db)
                conn_t.row_factory = sqlite3.Row
                conn_l = sqlite3.connect(tmp_lab_db)
                conn_l.row_factory = sqlite3.Row
                try:
                    records = reconcile_existing_db_rows(
                        snap_rows,
                        conn_t.cursor(),
                        conn_l.cursor(),
                        semester_id=semester_id,
                        year=sem_year,
                        season=sem_season,
                    )
                finally:
                    conn_t.close()
                    conn_l.close()

        if not records:
            raise JobError("EMPTY_DRAFT", "Reconcile compiled zero faculty schedules; aborting before live write.")

        upsert_res = upsert_via_psycopg2(
            records,
            db_url,
            semester_id=semester_id,
            audit_summary=audit_summary,
            audit_report_csv=csv_text,
            prune_stale=True,
            expected_state_version=expected_version,
            require_active=False,
            require_published=True,
            require_auto_enabled=False,
            use_monotonic_version_floor=True,
        )
        if upsert_res.get("aborted"):
            if upsert_res.get("reason") == "TOCTOU_STATE_VERSION_MISMATCH":
                return upsert_res
            raise JobError("RECONCILE_ABORTED", str(upsert_res.get("reason")))

        send_sync_callback(
            action="faculty_sync_callback",
            semester_id=semester_id,
            state_version=expected_version,
            status="SYNCED",
            error_message=None,
            portal_callback_url=portal_callback_url,
            callback_secret=callback_secret,
        )
        return upsert_res
    except BaseException as exc:
        err_code, err_msg = _classify_error(exc)
        try:
            send_sync_callback(
                action="faculty_sync_callback",
                semester_id=semester_id,
                state_version=expected_version,
                status="FAILED",
                error_message=f"{err_code}: {err_msg}",
                portal_callback_url=portal_callback_url,
                callback_secret=callback_secret,
            )
        except Exception as cb_err:
            print(f"[WARN] Failed to send FAILED faculty_sync_callback: {cb_err}")
        raise


# =============================================================================
# 7. MAIN EXECUTION
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="FAST Faculty Timetable Ingestion Pipeline (Multi-Semester)")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["draft", "refresh-draft", "sync", "reconcile-snapshot", "excel"],
        help="Explicit pipeline execution mode",
    )
    parser.add_argument("--job-id", type=str, default=None, help="Ingestion job UUID (for draft / refresh-draft)")
    parser.add_argument("--snapshot-id", type=str, default=None, help="Snapshot UUID (for reconcile-snapshot)")
    parser.add_argument("--expected-version", type=int, default=None, help="Expected semesters.state_version (for reconcile-snapshot)")
    parser.add_argument("--dry-run", action="store_true", help="Compile schedules without uploading to database")
    parser.add_argument("--year", type=int, default=2026, help="Academic year (for --mode excel)")
    parser.add_argument("--season", choices=["fall", "spring", "summer"], default="fall", help="Semester season (for --mode excel)")
    parser.add_argument("--semester-id", type=str, default="auto", help="Explicit semester slug or 'auto'")
    parser.add_argument("--excel", type=str, default=DEFAULT_EXCEL_PATH, help="Path to Course Allocation Excel workbook (for --mode excel)")
    parser.add_argument("--audit-report", type=str, default=None, help="Output path for CSV reconciliation report")
    parser.add_argument("--audit-json", type=str, default=None, help="Output path for JSON reconciliation summary")
    parser.add_argument("--theory-db", type=str, default=THEORY_DB_PATH, help="Path to theory timetable SQLite database")
    parser.add_argument("--lab-db", type=str, default=LAB_DB_PATH, help="Path to lab timetable SQLite database")
    args = parser.parse_args()

    db_url = get_database_url()
    supabase_url = (os.environ.get("SUPABASE_URL") or "").strip()
    service_role_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    callback_url = (os.environ.get("PORTAL_CALLBACK_URL") or "").strip()
    callback_secret = (os.environ.get("SYNC_CALLBACK_SECRET") or "").strip()

    if args.mode == "draft":
        if not args.job_id:
            print("[ERROR] --job-id is required for --mode draft", file=sys.stderr)
            sys.exit(2)
        if not db_url:
            print("[ERROR] DATABASE_URL is required for --mode draft", file=sys.stderr)
            sys.exit(1)
        try:
            run_draft_job(args.job_id, db_url, supabase_url, service_role_key)
        except BaseException as exc:
            print(f"[ERROR] Draft job failed: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    if args.mode == "refresh-draft":
        if not args.job_id:
            print("[ERROR] --job-id is required for --mode refresh-draft", file=sys.stderr)
            sys.exit(2)
        if not db_url:
            print("[ERROR] DATABASE_URL is required for --mode refresh-draft", file=sys.stderr)
            sys.exit(1)
        try:
            run_refresh_draft_job(args.job_id, db_url, supabase_url, service_role_key)
        except BaseException as exc:
            print(f"[ERROR] Refresh draft job failed: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    if args.mode == "reconcile-snapshot":
        if not args.snapshot_id or args.expected_version is None:
            print("[ERROR] --snapshot-id and --expected-version are required for --mode reconcile-snapshot", file=sys.stderr)
            sys.exit(2)
        if not db_url:
            print("[ERROR] DATABASE_URL is required for --mode reconcile-snapshot", file=sys.stderr)
            sys.exit(1)
        try:
            run_reconcile_snapshot(
                args.snapshot_id,
                args.expected_version,
                db_url,
                supabase_url=supabase_url,
                service_role_key=service_role_key,
                portal_callback_url=callback_url,
                callback_secret=callback_secret,
            )
        except BaseException as exc:
            print(f"[ERROR] Reconcile snapshot failed: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    if args.mode == "sync":
        if not db_url:
            print("[ERROR] DATABASE_URL not set. Continuous sync requires Supabase connection.", file=sys.stderr)
            sys.exit(1)
        sync_from_existing_database(
            db_url,
            theory_db=args.theory_db,
            lab_db=args.lab_db,
            dry_run=args.dry_run,
            semester_id=args.semester_id,
        )
        return

    if args.mode == "excel":
        excel_path = args.excel
        if not os.path.exists(excel_path):
            print(f"[ERROR] Course Allocation Excel workbook not found at '{excel_path}'", file=sys.stderr)
            sys.exit(1)

        if args.semester_id == "auto":
            if db_url:
                cfg = get_active_semester_config()
                semester_id = str(cfg["semester_id"])
                year = int(cfg.get("academic_year") or args.year)
                season_lower = str(cfg.get("season") or args.season).lower()
            elif is_ci_environment():
                print("[ERROR] DATABASE_URL is required when --semester-id auto in CI=true.", file=sys.stderr)
                sys.exit(1)
            else:
                year = args.year
                season_lower = (args.season or "fall").lower()
                semester_id = f"{year}-{season_lower}"
        else:
            year = args.year
            season_lower = (args.season or "fall").lower()
            semester_id = args.semester_id

        print("=== FAST Faculty Timetable Ingestion Pipeline (--mode excel) ===")
        print(f"Target Semester: {semester_id} (Year: {year}, Season: {season_lower})")

        faculty_roster = decode_faculty_bin(FACULTY_BIN_PATH)
        allocations = read_course_allocations(excel_path=excel_path, year=year, season=season_lower)
        records, audit_dict, csv_text = compile_faculty_schedules(
            allocations,
            faculty_roster,
            theory_db=args.theory_db,
            lab_db=args.lab_db,
            semester_id=semester_id,
            audit_csv_path=args.audit_report,
            audit_json_path=args.audit_json,
            return_audit=True,
            return_csv=True,
        )

        if args.dry_run:
            print(f"\n[DRY RUN] Compiled {len(records)} faculty schedules successfully for '{semester_id}'!")
            return

        if not db_url:
            print("[ERROR] DATABASE_URL not set. Run with --dry-run or configure .env.", file=sys.stderr)
            sys.exit(1)
        if not HAS_PSYCOPG2:
            print("[ERROR] psycopg2 is required for database sync. Please run: pip install psycopg2-binary", file=sys.stderr)
            sys.exit(1)

        upsert_via_psycopg2(
            records,
            db_url,
            semester_id=semester_id,
            audit_summary=audit_dict,
            audit_report_csv=csv_text,
            prune_stale=True,
        )


if __name__ == "__main__":
    main()

