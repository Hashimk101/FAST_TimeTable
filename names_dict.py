"""
Subject Name Mappings for University Timetable
===============================================
This module contains dictionaries that map between subject short forms
(as used in the timetable) and their full official names.

Usage:
    from subject_mappings import SHORT_TO_FULL, FULL_TO_SHORT

    full_name = SHORT_TO_FULL["DB"]  # Returns "Database Systems"
    short_form = FULL_TO_SHORT["Database Systems"]  # Returns "DB"
"""

# ==============================================================================
# SHORT FORM TO FULL NAME MAPPING
# ==============================================================================
# Maps the abbreviated subject codes used in the timetable to their full names
# Format: "Short Form": "Full Official Name"

SHORT_TO_FULL = {
    # --------------------------------------------------------------------------
    # SEMESTER 1 SUBJECTS (Fall 2024)
    # --------------------------------------------------------------------------
    "AP": "Applied Physics",                                    # NS1001
    "Calculus": "Calculus and Analytical Geometry",            # MT1003
    "Func Eng": "Functional English",                          # SS1012
    "Func Eng Lab": "Functional English - Lab",                # SL1012
    "Ideology of Pak": "Ideology and Constitution of Pakistan", # SS1013
    "IICT Lab": "Introduction to Information and Communication Technology", # CL1000
    "PF": "Programming Fundamentals",                          # CS1002
    "PF Lab": "Programming Fundamentals - Lab",                # CL1002

    # --------------------------------------------------------------------------
    # SEMESTER 2 SUBJECTS (Spring 2025)
    # --------------------------------------------------------------------------
    "Civics": "Civics and Community Engagement",               # SS2043
    "DLD": "Digital Logic Design",                             # EE1005
    "DLD Lab": "Digital Logic Design - Lab",                   # EL1005
    "Islamic": "Islamic Studies/Ethics",                       # SS1007 (can also be Ethics)
    "OOP": "Object Oriented Programming",                      # CS1004
    "OOP Lab": "Object Oriented Programming - Lab",            # CL1004

    # --------------------------------------------------------------------------
    # SEMESTER 3 SUBJECTS (Fall 2025)
    # --------------------------------------------------------------------------
    "COAL": "Computer Organization and Assembly Language",     # EE2003
    "COAL Lab": "Computer Organization and Assembly Language - Lab", # EL2003
    "Data St": "Data Structures",                              # CS2001
    "Data St Lab": "Data Structures - Lab",                    # CL2001
    "Discrete": "Discrete Structures",                         # CS1005
    "LA": "Linear Algebra",                                    # MT1004
    "Automata": "Theory of Automata",                          # CS3005

    # --------------------------------------------------------------------------
    # SEMESTER 4 SUBJECTS (Spring 2026)
    # --------------------------------------------------------------------------
    "ML": "Artificial Intelligence",                           # AI2002 (Note: ML is used for AI course)
    "ML Lab": "Artificial Intelligence - Lab",                 # AL2002
    "DB": "Database Systems",                                  # CS2005
    "DB Lab": "Database Systems - Lab",                        # CL2005
    "OS": "Operating Systems",                                 # CS2006
    "OS Lab": "Operating Systems - Lab",                       # CL2006
    "Prob & Stats": "Probability and Statistics",              # MT2005
    "Fund of SE": "Software Engineering",                      # CS3009

    # --------------------------------------------------------------------------
    # SEMESTER 5 SUBJECTS (Fall 2026)
    # --------------------------------------------------------------------------
    "Comp Net": "Computer Networks",                           # CS3001
    "Comp Net Lab": "Computer Networks - Lab",                 # CL3001
    "Algo": "Design and Analysis of Algorithms",               # CS2009
    "TBW": "Technical and Business Writing",                   # SS2007

    # --------------------------------------------------------------------------
    # SEMESTER 6 SUBJECTS (Spring 2027)
    # --------------------------------------------------------------------------
    "PDC": "Parallel and Distributed Computing",               # CS3006
    "S/w Const": "Compiler Construction",                      # CS4031
    "S/w Const Lab": "Compiler Construction - Lab",            # Related to CS4031

    # --------------------------------------------------------------------------
    # SEMESTER 7-8 SUBJECTS (Fall 2027 - Spring 2028)
    # --------------------------------------------------------------------------
    "Engg": "Entrepreneurship",                                # MG4011
    "Info Sec": "Information Security",                        # CS3002

    # --------------------------------------------------------------------------
    # ARTIFICIAL INTELLIGENCE & MACHINE LEARNING SUBJECTS
    # --------------------------------------------------------------------------
    # Advanced AI courses and specializations
    "Adv AI": "Advanced Artificial Intelligence",              # Advanced AI topics
    "Adv Gen AI": "Advanced Generative AI",                    # Advanced generative models
    "Gen AI": "Generative AI",                                 # Generative AI fundamentals
    "Agentic AI": "Agentic AI",                                # AI agents and autonomous systems
    "App ML": "Applied Machine Learning",                      # Practical ML applications
    "Deep Learning": "Deep Learning",                          # Neural networks and deep learning
    "NLP": "Natural Language Processing",                      # Text processing and language models
    "Comp Vision": "Computer Vision",                          # Image and video processing
    "Comp Vision Lab": "Computer Vision - Lab",                # CV lab component
    "Reinf Learning": "Reinforcement Learning",                # RL algorithms and applications
    "KRR": "Knowledge Representation and Reasoning",           # Symbolic AI and reasoning
    "Math Found of AI": "Mathematical Foundations of AI",      # Math prerequisites for AI
    "Prog for AI": "Programming for AI",                       # AI-specific programming
    "Prog for AI Lab": "Programming for AI - Lab",             # AI programming lab

    # --------------------------------------------------------------------------
    # DATA SCIENCE SUBJECTS
    # --------------------------------------------------------------------------
    # Data science and analytics courses
    "Intro to DS": "Introduction to Data Science",             # DS fundamentals
    "Intro to DS Lab": "Introduction to Data Science - Lab",   # DS lab component
    "DAV": "Data Analytics and Visualization",                 # Data analysis and viz
    "DAV Lab": "Data Analytics and Visualization - Lab",       # DAV lab component
    "Data Mining": "Data Mining",                              # Mining patterns from data
    "DW&BI": "Data Warehousing and Business Intelligence",     # DW and BI systems
    "DW&BI Lab": "Data Warehousing and Business Intelligence - Lab", # DW&BI lab
    "Stat & Math for DS": "Statistics and Mathematics for Data Science", # Stats for DS
    "Stat Modeling": "Statistical Modeling",                   # Statistical models
    "Data Sci Tools & Tech": "Data Science Tools and Techniques", # DS tools ecosystem

    # --------------------------------------------------------------------------
    # SOFTWARE ENGINEERING SUBJECTS
    # --------------------------------------------------------------------------
    # Software engineering and development courses
    "Intro to SE": "Introduction to Software Engineering",     # SE fundamentals
    "SDA": "Software Design and Architecture",                 # Design patterns and architecture
    "Adv S/w Arch": "Advanced Software Architecture",          # Advanced architectural patterns
    "S/w Qual Engg": "Software Quality Engineering",           # Quality assurance and testing
    "Adv Qual Assur": "Advanced Quality Assurance",            # Advanced QA techniques
    "Empirical S/w Engg": "Empirical Software Engineering",    # Evidence-based SE
    "Fund of SPM": "Fundamentals of Software Project Management", # Project management basics
    "Busi Proc Engg": "Business Process Engineering",          # Process modeling and optimization
    "SMD": "Software for Mobile Devices",                      # Mobile app development
    "User Exp": "User Experience",                             # UX design and usability

    # --------------------------------------------------------------------------
    # CYBERSECURITY SUBJECTS
    # --------------------------------------------------------------------------
    # Security, cryptography, and ethical hacking courses
    "Cy Sec": "Cybersecurity",                                 # General cybersecurity
    "Net Sec": "Network Security",                             # Network security protocols
    "Net Sec Lab": "Network Security - Lab",                   # Network security lab
    "Ethical Hack": "Ethical Hacking",                         # Penetration testing
    "Adv Digital Forensics": "Advanced Digital Forensics",     # Digital forensics and investigation
    "Info Assur": "Information Assurance",                     # IA principles and practices
    "App Info Sec": "Applied Information Security",            # Practical info security
    "Sec S/w Design": "Secure Software Design",                # Security in software design
    "Sec S/w Design Lab": "Secure Software Design - Lab",      # Secure design lab
    "Sec Sys Design": "Secure Systems Design",                 # Security architecture
    "Blockchain": "Blockchain Technology",                     # Blockchain and distributed ledgers

    # --------------------------------------------------------------------------
    # CLOUD COMPUTING & DEVOPS
    # --------------------------------------------------------------------------
    # Cloud platforms, operations, and MLOps courses
    "Cloud Comp": "Cloud Computing",                           # Cloud fundamentals (AWS, Azure, GCP)
    "Cloud MLOps": "Cloud MLOps",                              # ML operations in cloud
    "MLOps": "Machine Learning Operations",                    # MLOps practices
    "MLOPs": "Machine Learning Operations",                    # Alternate spelling
    "Hi Perf Comp": "High Performance Computing",              # HPC and parallel computing
    "Securing Cloud Comp": "Securing Cloud Computing",         # Cloud security

    # --------------------------------------------------------------------------
    # WEB & APPLICATION DEVELOPMENT
    # --------------------------------------------------------------------------
    # Web development and programming courses
    "Web": "Web Technologies",                                 # HTML, CSS, JavaScript
    "Web Prog": "Web Programming",                             # Web application development
    "App Prog": "Applied Programming",                         # Practical programming
    "DIP": "Digital Image Processing",                         # Image manipulation and processing
    "Game Design": "Game Design",                              # Game development fundamentals

    # --------------------------------------------------------------------------
    # ADVANCED COMPUTER SCIENCE SUBJECTS
    # --------------------------------------------------------------------------
    # Advanced topics in CS
    "Adv Algo": "Advanced Algorithms",                         # Advanced algorithmic techniques
    "Adv OS": "Advanced Operating Systems",                    # Advanced OS concepts

    # --------------------------------------------------------------------------
    # GENERAL/OTHER SUBJECTS
    # --------------------------------------------------------------------------
    # Mathematics, business, and soft skills
    "Numerical": "Numerical Computing/Analysis",               # Numerical methods
    "Psychology": "Psychology",                                # Psychology fundamentals
    "Research Methodology": "Research Methodology",            # Research methods and writing
    "Financial Mgt": "Financial Management",                   # Finance and accounting basics
    "PPIT": "Professional Practices in IT",                    # Professional ethics and practices
}


# ==============================================================================
# FULL NAME TO SHORT FORM MAPPING (REVERSE DICTIONARY)
# ==============================================================================
# Automatically generated reverse mapping from SHORT_TO_FULL
# Maps full official names back to their short forms
# Format: "Full Official Name": "Short Form"

FULL_TO_SHORT = {v: k for k, v in SHORT_TO_FULL.items()}


# ==============================================================================
# ADDITIONAL ALIASES
# ==============================================================================
# Common variations and alternative names that students might use
# These provide additional ways to look up subjects
# Format: "Alternative Name": "Short Form"

ALIASES = {
    # Common alternative names that map to the same short forms
    "Programming Fundamentals": "PF",                          # Explicit mapping
    "Object Oriented Programming": "OOP",                      # Full name variant
    "Data Structures": "Data St",                              # Without "and Algorithms"
    "Database Systems": "DB",                                  # Singular/plural variations
    "Operating Systems": "OS",                                 # Plural form
    "Computer Networks": "Comp Net",                           # Without "and Communications"
    "Artificial Intelligence": "ML",                           # Official AI course
    "Machine Learning": "ML",                                  # ML is subset of AI but same code
    "Design and Analysis of Algorithms": "Algo",               # Full formal name
    "Digital Logic Design": "DLD",                             # Electronics course
    "Computer Organization and Assembly Language": "COAL",     # Computer architecture
    "Discrete Structures": "Discrete",                         # Math for CS
    "Linear Algebra": "LA",                                    # Matrix theory
    "Probability and Statistics": "Prob & Stats",              # Stats course
    "Software Engineering": "Fund of SE",                      # SE fundamentals
    "Theory of Automata": "Automata",                          # Formal languages
    "Technical and Business Writing": "TBW",                   # Communication course
    "Information Security": "Info Sec",                        # Security fundamentals
    "Parallel and Distributed Computing": "PDC",               # Distributed systems
    "Compiler Construction": "S/w Const",                      # Compiler design
    "Islamic Studies": "Islamic",                              # Religious studies
    "Ethics": "Islamic",                                       # Can take either Islamic or Ethics
    "Functional English": "Func Eng",                          # English communication
    "Applied Physics": "AP",                                   # Physics for CS
    "Calculus and Analytical Geometry": "Calculus",            # Calculus I
}


# ==============================================================================
# NOTES ON USAGE
# ==============================================================================
"""
IMPORTANT NOTES:

1. Some subjects have multiple offerings (e.g., PF (CS-A), PF (CS-B))
   - The section identifiers (CS-A, CS-B, etc.) are NOT included in this mapping
   - They represent different sections of the same course

2. Lab components are separate entries:
   - "PF" = Programming Fundamentals (Lecture)
   - "PF Lab" = Programming Fundamentals (Lab)

3. "ML" is used for "Artificial Intelligence" in the timetable:
   - This is the course code AI2002
   - The timetable uses "ML" as shorthand

4. Some subjects may have alternate spellings:
   - "MLOps" and "MLOPs" both map to the same course

5. Elective courses:
   - Generic electives like "CSX01" are not included
   - Only specific named courses are mapped

6. Social Science and Islamic Studies:
   - "Islamic" can refer to either Islamic Studies OR Ethics (student chooses)

EXAMPLE USAGE:

    # Get full name from short form
    full_name = SHORT_TO_FULL.get("DB", "Unknown")
    # Returns: "Database Systems"

    # Get short form from full name
    short_form = FULL_TO_SHORT.get("Database Systems", "Unknown")
    # Returns: "DB"

    # Check if subject exists
    if "PF" in SHORT_TO_FULL:
        print(f"PF stands for: {SHORT_TO_FULL['PF']}")

    # Use with default value for safety
    subject = SHORT_TO_FULL.get("XYZ", "Subject not found")
"""
