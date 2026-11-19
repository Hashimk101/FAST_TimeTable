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
import json
import base64
import hashlib
import sqlite3
import unicodedata
from typing import Dict, List, Optional, Tuple, Set, Any, Union
from datetime import datetime, timezone

try:
    import openpyxl
except ImportError:
    sys.exit("[ERROR] openpyxl not found. Please run: pip install openpyxl")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

import requests

# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

DEFAULT_EXCEL_PATH = "Course Allocation - Fall-2026, School of Computing.xlsx"
FACULTY_BIN_PATH = os.path.join("frontend", "data", "faculty.bin")
THEORY_DB_PATH = "uni_timetable.db"
LAB_DB_PATH = "uni_timetable_lab.db"

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
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Course Allocation workbook not found at: {excel_path}")

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

            sec_info = translate_section_code(sec_str, year=year, season=season)
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

    def export_csv(self, filepath: str):
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
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


def compile_faculty_schedules(
    allocations: List[Dict[str, Any]], 
    faculty_roster: List[Dict[str, Any]],
    theory_db: str = THEORY_DB_PATH,
    lab_db: str = LAB_DB_PATH,
    semester_id: str = "2026-fall",
    audit_csv_path: Optional[str] = "reconciliation_report.csv",
    audit_json_path: Optional[str] = "reconciliation_summary.json",
    return_audit: bool = False
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Dict[str, Any]]]:
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

    def parse_time_minutes(t_str: str) -> int:
        try:
            parts = t_str.split(":")
            h, m = int(parts[0]), int(parts[1])
            if 1 <= h <= 7:
                h += 12
            return h * 60 + m
        except Exception:
            return 0

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
                    "sections": set()
                }
                total_credit_hours += chs
            if sec_name:
                unique_courses_map[c_key]["sections"].add(sec_name)

            base_subj = canonical_subj.replace(" Lab", "").strip() if canonical_subj else ""
            if canonical_subj in ("UHQ-II", "UHQ-I&II", "UHQ-I & II"):
                base_subj = "UHQ-I&II" if canonical_subj == "UHQ-II" else "UHQ-II"
                subj_cond = "(SUBJECT = ? OR SUBJECT = ? OR SUBJECT = ? OR SUBJECT LIKE ? OR SUBJECT LIKE ?)"
                subj_params = ("UHQ-II", "UHQ-I&II", "UHQ-I & II", "%UHQ-II%", "%UHQ-I%II%")
            elif len(canonical_subj) <= 3:
                # Issue 04: Short Acronym Wildcard Collision Guard
                subj_cond = "(SUBJECT = ? OR SUBJECT = ?)"
                subj_params = (canonical_subj, base_subj)
            else:
                subj_cond = "(SUBJECT = ? OR SUBJECT LIKE ? OR SUBJECT = ? OR SUBJECT LIKE ?)"
                subj_params = (canonical_subj, f"%{canonical_subj}%", base_subj, f"%{base_subj}%")
            disc = sec_name.split("-")[0] if (sec_name and "-" in sec_name) else ""
            letter = sec_name.split("-")[1] if (sec_name and "-" in sec_name) else ""

            # Issue 10: Strict Domain Isolation - NO Cross-DB Leaks
            cursors_to_try = [
                (cur_lab, "LAB", True)
            ] if is_lab else [
                (cur_theory, "CLASSROOM", False)
            ]

            rows = []
            final_is_lab = is_lab

            for target_cursor, location_col, actual_lab in cursors_to_try:
                select_clause = f"SELECT ID, DAY, START_TIME, END_TIME, SUBJECT, {location_col} AS LOCATION, SECTION, BATCH, STATUS FROM timetable"

                queries_to_try = []

                if b_name:
                    # 1. Exact batch + exact/substring section
                    queries_to_try.append({
                        "query": f"{select_clause} WHERE BATCH = ? AND (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
                        "params": (b_name, sec_name, f"%{sec_name}%") + subj_params
                    })
                    # 2. Combined section in exact batch (e.g. CS/CY-A)
                    if disc and letter:
                        queries_to_try.append({
                            "query": f"{select_clause} WHERE BATCH = ? AND SECTION LIKE ? AND SECTION LIKE ? AND {subj_cond}",
                            "params": (b_name, f"%{disc}%", f"%{letter}%") + subj_params
                        })
                    # 3. Exact batch with blank/null section (open pool senior electives e.g. Fund of SPM, SMD, Agentic AI)
                    queries_to_try.append({
                        "query": f"{select_clause} WHERE BATCH = ? AND (SECTION = '' OR SECTION IS NULL) AND (SUBJECT = ? OR SUBJECT LIKE ?)",
                        "params": (b_name, canonical_subj, f"%{canonical_subj}%")
                    })
                    queries_to_try.append({
                        "query": f"{select_clause} WHERE BATCH = ? AND (SECTION = '' OR SECTION IS NULL) AND {subj_cond}",
                        "params": (b_name,) + subj_params
                    })
                    # 4. Fallback to 'BS Repeat Courses'
                    queries_to_try.append({
                        "query": f"{select_clause} WHERE BATCH = 'BS Repeat Courses' AND (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
                        "params": (sec_name, f"%{sec_name}%") + subj_params
                    })
                    if disc and letter:
                        queries_to_try.append({
                            "query": f"{select_clause} WHERE BATCH = 'BS Repeat Courses' AND SECTION LIKE ? AND SECTION LIKE ? AND {subj_cond}",
                            "params": (f"%{disc}%", f"%{letter}%") + subj_params
                        })
                    # 5. Fallback to 'BS Repeat Courses' with blank/null section (elective courses)
                    queries_to_try.append({
                        "query": f"{select_clause} WHERE BATCH = 'BS Repeat Courses' AND (SECTION = '' OR SECTION IS NULL) AND {subj_cond}",
                        "params": subj_params
                    })

                    # 5b. Fallback for Graduate / MS / PhD Programs (dedicated batch, elective pools, or open graduate slots)
                    if b_name.startswith("MS") or b_name.startswith("PhD"):
                        queries_to_try.append({
                            "query": f"{select_clause} WHERE (BATCH = 'MS Electives (All Prgrms)' OR BATCH LIKE 'MS%' OR BATCH LIKE 'PhD%') AND (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
                            "params": (sec_name, f"%{sec_name}%") + subj_params
                        })
                        queries_to_try.append({
                            "query": f"{select_clause} WHERE (BATCH = 'MS Electives (All Prgrms)' OR BATCH LIKE 'MS%' OR BATCH LIKE 'PhD%') AND {subj_cond}",
                            "params": subj_params
                        })

                # 6. Final Fallback (Ignore batch completely with section)
                queries_to_try.append({
                    "query": f"{select_clause} WHERE (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
                    "params": (sec_name, f"%{sec_name}%") + subj_params
                })
                if disc and letter:
                    queries_to_try.append({
                        "query": f"{select_clause} WHERE SECTION LIKE ? AND SECTION LIKE ? AND {subj_cond}",
                        "params": (f"%{disc}%", f"%{letter}%") + subj_params
                    })
                # 7. Final Fallback (Ignore batch completely with blank/null section)
                queries_to_try.append({
                    "query": f"{select_clause} WHERE (SECTION = '' OR SECTION IS NULL) AND (SUBJECT = ? OR SUBJECT LIKE ?)",
                    "params": (canonical_subj, f"%{canonical_subj}%")
                })
                queries_to_try.append({
                    "query": f"{select_clause} WHERE (SECTION = '' OR SECTION IS NULL) AND {subj_cond}",
                    "params": subj_params
                })

                for attempt in queries_to_try:
                    target_cursor.execute(attempt["query"], attempt["params"])
                    fetched = target_cursor.fetchall()
                    if fetched:
                        rows = fetched
                        final_is_lab = actual_lab
                        break

                if rows:
                    break

            if rows:
                auditor.record_allocation_matched(alloc, fac_info, email, rows, final_is_lab)
                for row in rows:
                    auditor.record_claimed_slot(final_is_lab, row["ID"])
            else:
                auditor.record_allocation_unmatched(alloc, fac_info, email, cur_theory, cur_lab)

            for row in rows:
                day = row["DAY"]
                if day not in weekly_schedule:
                    continue

                raw_status = str(row["STATUS"] or "").strip()
                is_cancelled = "cancel" in raw_status.lower() if raw_status else False

                # Issue 09: Faculty Clean Section Badging
                clean_sec = sec_name if sec_name else format_clean_section(str(row["SECTION"] or ""))

                slot_entry = {
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
                    "is_cancelled": is_cancelled
                }

                duplicate_found = False
                for existing in weekly_schedule[day]:
                    if (existing["start_time"] == slot_entry["start_time"] and 
                        existing["end_time"] == slot_entry["end_time"] and
                        existing["subject"] == slot_entry["subject"]):
                        if clean_sec:
                            existing_secs = [s.strip() for s in existing["section"].split(",") if s.strip()]
                            for s_part in clean_sec.split(","):
                                s_part = s_part.strip()
                                if s_part and s_part not in existing_secs:
                                    existing_secs.append(s_part)
                            existing["section"] = ", ".join(sorted(existing_secs))
                        if is_cancelled:
                            existing["is_cancelled"] = True
                        duplicate_found = True
                        break

                if not duplicate_found:
                    weekly_schedule[day].append(slot_entry)
                    total_slots += 1

        for day in DAYS_OF_WEEK:
            weekly_schedule[day].sort(key=lambda s: parse_time_minutes(s["start_time"]))

        courses_summary = []
        for c in unique_courses_map.values():
            courses_summary.append({
                "course_code": c["course_code"],
                "course_name": c["course_name"],
                "canonical_subject": c["canonical_subject"],
                "credit_hours": c["credit_hours"],
                "is_lab": c["is_lab"],
                "sections": sorted(list(c["sections"]))
            })
        courses_summary.sort(key=lambda x: x["course_code"])

        payload_for_hashing = {
            "schedule": weekly_schedule,
            "courses": courses_summary
        }
        hash_digest = hashlib.sha256(
            json.dumps(payload_for_hashing, sort_keys=True).encode("utf-8")
        ).hexdigest()

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

    conn_theory.close()
    conn_lab.close()

    print(f"Compiled weekly schedules for {len(compiled_records)} faculty members.")
    if return_audit:
        return compiled_records, auditor.get_summary_dict()
    return compiled_records

# =============================================================================
# 5. ATOMIC UPSERT ENGINE (POSTGRESQL OR REST FALLBACK)
# =============================================================================

def upsert_via_psycopg2(records: List[Dict[str, Any]], database_url: str, semester_id: str = "2026-fall"):
    """Atomic upsert via PostgreSQL connection pooler."""
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    cursor = conn.cursor()

    stats = {"inserted": 0, "updated": 0, "unchanged": 0}

    upsert_query = """
        INSERT INTO public.faculty_schedules (
            email, semester_id, name, designation, department, office,
            schedule, courses, total_weekly_slots, total_credit_hours,
            schedule_hash, version
        )
        VALUES (
            %(email)s, %(semester_id)s, %(name)s, %(designation)s, %(department)s, %(office)s,
            %(schedule)s, %(courses)s, %(total_weekly_slots)s, %(total_credit_hours)s,
            %(schedule_hash)s, 1
        )
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
                ELSE public.faculty_schedules.version + 1
            END,
            schedule_hash = EXCLUDED.schedule_hash,
            updated_at = CASE
                WHEN public.faculty_schedules.schedule_hash = EXCLUDED.schedule_hash THEN public.faculty_schedules.updated_at
                ELSE timezone('utc'::text, now())
            END
        RETURNING (xmax = 0) AS is_insert;
    """

    try:
        for rec in records:
            params = {
                "email": rec["email"],
                "semester_id": rec.get("semester_id", semester_id),
                "name": rec["name"],
                "designation": rec["designation"],
                "department": rec["department"],
                "office": rec["office"],
                "schedule": json.dumps(rec["schedule"]),
                "courses": json.dumps(rec["courses"]),
                "total_weekly_slots": rec["total_weekly_slots"],
                "total_credit_hours": rec["total_credit_hours"],
                "schedule_hash": rec["schedule_hash"]
            }
            cursor.execute(upsert_query, params)
            row = cursor.fetchone()
            if row:
                is_insert = row[0]
                if is_insert:
                    stats["inserted"] += 1
                else:
                    stats["updated"] += 1

        conn.commit()
        print(f"\n[SUCCESS] Supabase Synchronization Complete:")
        print(f"  - New Profiles Inserted: {stats['inserted']}")
        print(f"  - Profiles Upserted: {stats['updated']}")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Failed to upsert to Supabase: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

# =============================================================================
# 6. CONTINUOUS SYNC FROM DATABASE (When Excel is absent)
# =============================================================================

def sync_from_existing_database(
    db_url: str,
    theory_db: str = THEORY_DB_PATH,
    lab_db: str = LAB_DB_PATH,
    dry_run: bool = False,
    semester_id: str = "2026-fall"
):
    """
    Continuous synchronization mode when Course Allocation Excel sheet is absent.
    Reads existing faculty records from Supabase for the specified semester_id,
    re-queries uni_timetable.db and uni_timetable_lab.db for each teacher's assigned classes,
    and updates Supabase only if room/timing changes occur.
    """
    if not HAS_PSYCOPG2:
        sys.exit("[ERROR] psycopg2 is required for database sync. Run: pip install psycopg2-binary")

    conn_db = psycopg2.connect(db_url)
    cur_db = conn_db.cursor(cursor_factory=RealDictCursor)
    
    cur_db.execute("""
        SELECT email, semester_id, name, designation, department, office, schedule, courses, schedule_hash, version, total_credit_hours
        FROM faculty_schedules
        WHERE semester_id = %s
    """, (semester_id,))
    rows = cur_db.fetchall()
    cur_db.close()
    conn_db.close()

    if not rows:
        print(f"[WARN] No existing faculty profiles found in Supabase for semester '{semester_id}'.")
        return

    print(f"Loaded {len(rows)} faculty profiles from Supabase for semester '{semester_id}' continuous synchronization.")

    conn_theory = sqlite3.connect(theory_db)
    conn_theory.row_factory = sqlite3.Row
    cur_theory = conn_theory.cursor()

    conn_lab = sqlite3.connect(lab_db)
    conn_lab.row_factory = sqlite3.Row
    cur_lab = conn_lab.cursor()

    def parse_time_minutes(t_str: str) -> int:
        try:
            parts = t_str.split(":")
            h, m = int(parts[0]), int(parts[1])
            if 1 <= h <= 7:
                h += 12
            return h * 60 + m
        except Exception:
            return 0

    updated_records = []

    for row in rows:
        email = row["email"]
        existing_schedule = row["schedule"] or {}
        
        # 1. Preserve top-level metadata keys (e.g. custom_activities list, slot_overrides)
        extra_keys = {
            k: v for k, v in existing_schedule.items()
            if k not in DAYS_OF_WEEK
        }

        # 2. Extract custom activities from day arrays (Office hours, FYP, meetings, etc.)
        custom_day_activities = {day: [] for day in DAYS_OF_WEEK}
        assigned_classes = {}

        for day in DAYS_OF_WEEK:
            slots = existing_schedule.get(day, [])
            if not isinstance(slots, list):
                continue
            for s in slots:
                if not isinstance(s, dict):
                    continue

                # Check if it is a custom academic activity
                is_custom = (
                    s.get("isCustom") is True
                    or bool(s.get("customCategory"))
                    or str(s.get("id", "")).startswith("act")
                )

                if is_custom:
                    custom_day_activities[day].append(s)
                    continue

                # Official university course
                s_batch = s.get("batch") or ""
                s_sec = str(s.get("section") or "").strip()
                s_subj = str(s.get("subject") or "").strip()
                s_lab = bool(s.get("is_lab", False))

                if not s_subj:
                    continue

                key = (s_batch, s_sec, s_subj, s_lab)
                if key not in assigned_classes:
                    assigned_classes[key] = {
                        "batch": s_batch,
                        "section": s_sec,
                        "subject": s_subj,
                        "is_lab": s_lab,
                        "course_code": s.get("course_code", "") or "",
                        "course_name": s.get("course_name", "") or ""
                    }

        weekly_schedule = {day: [] for day in DAYS_OF_WEEK}
        total_slots = 0

        for key, cls_info in assigned_classes.items():
            b_name = cls_info.get("batch") or ""
            sec_name = str(cls_info.get("section") or "").strip()
            canonical_subj = str(cls_info.get("subject") or "").strip()
            is_lab = bool(cls_info.get("is_lab", False))
            c_code = cls_info.get("course_code") or ""
            c_title = cls_info.get("course_name") or ""

            if not canonical_subj:
                continue

            base_subj = canonical_subj.replace(" Lab", "").strip() if canonical_subj else ""
            if canonical_subj in ("UHQ-II", "UHQ-I&II", "UHQ-I & II"):
                base_subj = "UHQ-I&II" if canonical_subj == "UHQ-II" else "UHQ-II"
                subj_cond = "(SUBJECT = ? OR SUBJECT = ? OR SUBJECT = ? OR SUBJECT LIKE ? OR SUBJECT LIKE ?)"
                subj_params = ("UHQ-II", "UHQ-I&II", "UHQ-I & II", "%UHQ-II%", "%UHQ-I%II%")
            elif len(canonical_subj) <= 3:
                # Issue 04: Short Acronym Wildcard Collision Guard
                subj_cond = "(SUBJECT = ? OR SUBJECT = ?)"
                subj_params = (canonical_subj, base_subj)
            else:
                subj_cond = "(SUBJECT = ? OR SUBJECT LIKE ? OR SUBJECT = ? OR SUBJECT LIKE ?)"
                subj_params = (canonical_subj, f"%{canonical_subj}%", base_subj, f"%{base_subj}%")
            disc = sec_name.split("-")[0] if (sec_name and "-" in sec_name) else ""
            letter = sec_name.split("-")[1] if (sec_name and "-" in sec_name) else ""

            # Issue 10: Strict Domain Isolation - NO Cross-DB Leaks
            cursors_to_try = [
                (cur_lab, "LAB", True)
            ] if is_lab else [
                (cur_theory, "CLASSROOM", False)
            ]

            matches = []
            final_is_lab = is_lab

            for target_cursor, location_col, actual_lab in cursors_to_try:
                select_clause = f"SELECT ID, DAY, START_TIME, END_TIME, SUBJECT, {location_col} AS LOCATION, SECTION, BATCH, STATUS FROM timetable"

                queries_to_try = []

                if b_name:
                    queries_to_try.append({
                        "query": f"{select_clause} WHERE BATCH = ? AND (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
                        "params": (b_name, sec_name, f"%{sec_name}%") + subj_params
                    })
                    if disc and letter:
                        queries_to_try.append({
                            "query": f"{select_clause} WHERE BATCH = ? AND SECTION LIKE ? AND SECTION LIKE ? AND {subj_cond}",
                            "params": (b_name, f"%{disc}%", f"%{letter}%") + subj_params
                        })
                    # Issue 02: Exact batch with blank/null section (open pool senior electives e.g. Fund of SPM, SMD, Deep Learn, Agentic AI)
                    queries_to_try.append({
                        "query": f"{select_clause} WHERE BATCH = ? AND (SECTION = '' OR SECTION IS NULL) AND (SUBJECT = ? OR SUBJECT LIKE ?)",
                        "params": (b_name, canonical_subj, f"%{canonical_subj}%")
                    })
                    queries_to_try.append({
                        "query": f"{select_clause} WHERE BATCH = ? AND (SECTION = '' OR SECTION IS NULL) AND {subj_cond}",
                        "params": (b_name,) + subj_params
                    })
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

                    # Fallback for Graduate / MS / PhD Programs
                    if b_name and (b_name.startswith("MS") or b_name.startswith("PhD")):
                        queries_to_try.append({
                            "query": f"{select_clause} WHERE (BATCH = 'MS Electives (All Prgrms)' OR BATCH LIKE 'MS%' OR BATCH LIKE 'PhD%') AND (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
                            "params": (sec_name, f"%{sec_name}%") + subj_params
                        })
                        queries_to_try.append({
                            "query": f"{select_clause} WHERE (BATCH = 'MS Electives (All Prgrms)' OR BATCH LIKE 'MS%' OR BATCH LIKE 'PhD%') AND {subj_cond}",
                            "params": subj_params
                        })

                queries_to_try.append({
                    "query": f"{select_clause} WHERE (SECTION = ? OR SECTION LIKE ?) AND {subj_cond}",
                    "params": (sec_name, f"%{sec_name}%") + subj_params
                })
                if disc and letter:
                    queries_to_try.append({
                        "query": f"{select_clause} WHERE SECTION LIKE ? AND SECTION LIKE ? AND {subj_cond}",
                        "params": (f"%{disc}%", f"%{letter}%") + subj_params
                    })

                # Final Fallback (Ignore batch completely with blank/null section)
                queries_to_try.append({
                    "query": f"{select_clause} WHERE (SECTION = '' OR SECTION IS NULL) AND (SUBJECT = ? OR SUBJECT LIKE ?)",
                    "params": (canonical_subj, f"%{canonical_subj}%")
                })
                queries_to_try.append({
                    "query": f"{select_clause} WHERE (SECTION = '' OR SECTION IS NULL) AND {subj_cond}",
                    "params": subj_params
                })

                for attempt in queries_to_try:
                    target_cursor.execute(attempt["query"], attempt["params"])
                    fetched = target_cursor.fetchall()
                    if fetched:
                        matches = fetched
                        final_is_lab = actual_lab
                        break

                if matches:
                    break

            for m in matches:
                m_day = m["DAY"]
                if m_day in weekly_schedule:
                    m_status = str(m["STATUS"] or "").strip()
                    is_cancelled = "cancel" in m_status.lower() if m_status else False
                    clean_sec = sec_name if sec_name else format_clean_section(str(m["SECTION"] or ""))

                    slot_entry = {
                        "course_code": c_code,
                        "course_name": c_title,
                        "subject": m["SUBJECT"],
                        "batch": m["BATCH"],
                        "section": clean_sec,
                        "is_lab": final_is_lab,
                        "start_time": m["START_TIME"],
                        "end_time": m["END_TIME"],
                        "location": m["LOCATION"],
                        "status": m["STATUS"],
                        "is_cancelled": is_cancelled
                    }
                    duplicate_found = False
                    for existing in weekly_schedule[m_day]:
                        if (existing["start_time"] == slot_entry["start_time"] and 
                            existing["end_time"] == slot_entry["end_time"] and
                            existing["subject"] == slot_entry["subject"]):
                            if clean_sec:
                                existing_secs = [s.strip() for s in existing["section"].split(",") if s.strip()]
                                for s_part in clean_sec.split(","):
                                    s_part = s_part.strip()
                                    if s_part and s_part not in existing_secs:
                                        existing_secs.append(s_part)
                                existing["section"] = ", ".join(sorted(existing_secs))
                            if is_cancelled:
                                existing["is_cancelled"] = True
                            duplicate_found = True
                            break

                    if not duplicate_found:
                        weekly_schedule[m_day].append(slot_entry)
                        total_slots += 1

        # 3. Merge custom activities back in and sort
        for day in DAYS_OF_WEEK:
            for custom_act in custom_day_activities[day]:
                if custom_act not in weekly_schedule[day]:
                    weekly_schedule[day].append(custom_act)
                    total_slots += 1
            weekly_schedule[day].sort(key=lambda s: parse_time_minutes(str(s.get("start_time") or "00:00")))

        # 4. Re-attach extra metadata (e.g. custom_activities list, slot_overrides)
        for k, v in extra_keys.items():
            weekly_schedule[k] = v

        schedule_canonical_str = json.dumps(weekly_schedule, sort_keys=True)
        new_hash = hashlib.sha256(schedule_canonical_str.encode("utf-8")).hexdigest()

        updated_records.append({
            "email": email,
            "semester_id": row.get("semester_id", semester_id),
            "name": row["name"],
            "designation": row["designation"],
            "department": row["department"],
            "office": row["office"],
            "schedule": weekly_schedule,
            "courses": row["courses"],
            "total_weekly_slots": total_slots,
            "total_credit_hours": row.get("total_credit_hours", 0),
            "schedule_hash": new_hash
        })

    conn_theory.close()
    conn_lab.close()

    if dry_run:
        print(f"\n[DRY RUN] Successfully processed {len(updated_records)} faculty profiles from Supabase for semester '{semester_id}'.")
        return

    upsert_via_psycopg2(updated_records, db_url, semester_id=semester_id)

# =============================================================================
# 7. MAIN EXECUTION
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="FAST Faculty Timetable Ingestion Pipeline (Multi-Semester)")
    parser.add_argument("--dry-run", action="store_true", help="Compile schedules without uploading to database")
    parser.add_argument("--year", type=int, default=2026, help="Academic year (e.g. 2026, 2027)")
    parser.add_argument("--season", choices=["fall", "spring", "summer"], default="fall", help="Semester season")
    parser.add_argument("--semester-id", type=str, default=None, help="Explicit semester slug (e.g. 2026-fall, 2027-spring)")
    parser.add_argument("--excel", type=str, default=DEFAULT_EXCEL_PATH, help="Path to Course Allocation Excel workbook")
    parser.add_argument("--audit-report", type=str, default="reconciliation_report.csv", help="Output path for CSV reconciliation report")
    parser.add_argument("--audit-json", type=str, default="reconciliation_summary.json", help="Output path for JSON reconciliation summary")
    args = parser.parse_args()

    semester_id = args.semester_id or f"{args.year}-{args.season.lower()}"
    excel_path = args.excel

    # Load DATABASE_URL from .env if present
    db_url = os.environ.get("DATABASE_URL")
    if not db_url and os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("DATABASE_URL="):
                    db_url = line.split("=", 1)[1].strip().strip("'\"")
                    break

    print("=== FAST Faculty Timetable Ingestion Pipeline ===")
    print(f"Target Semester: {semester_id} (Year: {args.year}, Season: {args.season})")
    
    excel_exists = os.path.exists(excel_path)
    
    if excel_exists:
        print(f"[MODE] Found '{excel_path}'. Performing full allocation ingestion.")
        faculty_roster = decode_faculty_bin()
        allocations = read_course_allocations(excel_path=excel_path, year=args.year, season=args.season)
        records = compile_faculty_schedules(
            allocations, 
            faculty_roster, 
            semester_id=semester_id,
            audit_csv_path=args.audit_report,
            audit_json_path=args.audit_json
        )

        if args.dry_run:
            print(f"\n[DRY RUN] Compiled {len(records)} faculty schedules successfully for '{semester_id}'!")
            if records:
                sample = records[0]
                print(f"\nSample Teacher: {sample['name']} ({sample['email']})")
                print(f"Semester: {sample['semester_id']}")
                print(f"Department: {sample['department']}")
                print(f"Weekly Slots: {sample['total_weekly_slots']}")
                print(f"Credit Hours: {sample['total_credit_hours']}")
                print(f"Schedule Preview: {json.dumps(sample['courses'], indent=2)}")
            return

        if not db_url:
            print("[ERROR] DATABASE_URL not set. Run with --dry-run or configure .env.")
            sys.exit(1)

        if HAS_PSYCOPG2:
            upsert_via_psycopg2(records, db_url, semester_id=semester_id)
        else:
            print("[ERROR] psycopg2 is required for database sync. Please run: pip install psycopg2-binary")
            sys.exit(1)
    else:
        print(f"[MODE] '{excel_path}' not present. Performing continuous timetable synchronization from Supabase.")
        if not db_url:
            print("[ERROR] DATABASE_URL not set. Continuous sync requires Supabase connection.")
            sys.exit(1)
        sync_from_existing_database(db_url, dry_run=args.dry_run, semester_id=semester_id)

if __name__ == "__main__":
    main()

