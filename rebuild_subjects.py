import sqlite3

# Mapping: (Full Name, Semester, Short Name)
subjects = [
    # Semester 1
    ("Applied Physics", 1, "AP"),
    ("Calculus and Analytical Geometry", 1, "Calculus"),
    ("Functional English", 1, "Functional English"),
    ("Functional English - Lab", 1, "Functional English Lab"),
    ("Ideology and Constitution of Pakistan", 1, "Ideology of Pak"),
    ("Introduction to Information and Communication Technology", 1, "IICT Lab"),
    ("Programming Fundamentals", 1, "PF"),
    ("Programming Fundamentals - Lab", 1, "PF Lab"),
    ("Understanding Holy Quran", 1, "UHQ-I"),
    
    # Semester 2
    ("Civics and Community Engagement", 2, "Civics"),
    ("Digital Logic Design", 2, "DLD"),
    ("Digital Logic Design - Lab", 2, "DLD Lab"),
    ("Expository Writing", 2, "Exp Writing"),
    ("Expository Writing - Lab", 2, "Exp Writing Lab"),
    ("Islamic Studies/Ethics", 2, "Islamic Studies"),
    ("Multivariable Calculus", 2, "MV Calculus"),
    ("Object Oriented Programming", 2, "OOP"),
    ("Object Oriented Programming - Lab", 2, "OOP Lab"),
    ("Understanding Sirat-Un-Nabi (PBUH)", 2, "Seerah & UHQ-I"),
    
    # Semester 3
    ("Computer Organization and Assembly Language", 3, "COAL"),
    ("Computer Organization and Assembly Language - Lab", 3, "COAL Lab"),
    ("Data Structures", 3, "Data St"),
    ("Data Structures - Lab", 3, "Data St Lab"),
    ("Discrete Structures", 3, "Discrete"),
    ("Linear Algebra", 3, "LA"),
    ("Theory of Automata", 3, "Automata"),
    
    # Semester 4
    ("Artificial Intelligence", 4, "AI"),
    ("Artificial Intelligence - Lab", 4, "AI Lab"),
    ("Database Systems", 4, "DB"),
    ("Database Systems - Lab", 4, "DB Lab"),
    ("Operating Systems", 4, "OS"),
    ("Operating Systems - Lab", 4, "OS Lab"),
    ("Pakistan Studies", 4, "Pak Studies"),
    ("Probability and Statistics", 4, "Prob & Stats"),
    ("Software Engineering", 4, "SE"),
    
    # Semester 5
    ("Applied Human Computer Interaction", 5, "Applied HCI"),
    ("Computer Architecture", 5, "Comp Arch"),
    ("Computer Networks", 5, "Comp Net"),
    ("Computer Networks - Lab", 5, "Comp Net Lab"),
    ("Design and Analysis of Algorithms", 5, "Algo"),
    ("Technical and Business Writing", 5, "TBW"),
    
    # Semester 6
    ("Advanced DBMS", 6, "Adv DBMS"),
    ("Compiler Construction", 6, "Comp Const"),
    ("Parallel and Distributed Computing", 6, "PDC"),
    
    # Semester 7
    ("Entrepreneurship", 7, "Entre"),
    ("Final Year Project - I", 7, "FYP-I"),
    
    # Semester 8
    ("Final Year Project - II", 8, "FYP-II"),
    ("Information Security", 8, "Info Sec"),
    ("Professional Practices in IT", 8, "PPIT")
]

def rebuild_subjects_db():
    conn = sqlite3.connect('subjects.db')
    cursor = conn.cursor()
    
    # Recreate table
    cursor.execute('DROP TABLE IF EXISTS subjects')
    cursor.execute('''
        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            semester INTEGER NOT NULL,
            short_name TEXT NOT NULL
        )
    ''')
    
    # Insert new subjects
    cursor.executemany('INSERT INTO subjects (name, semester, short_name) VALUES (?, ?, ?)', subjects)
    
    conn.commit()
    conn.close()
    print(f"Successfully inserted {len(subjects)} subjects into subjects.db with shorthands")

if __name__ == "__main__":
    rebuild_subjects_db()
