import sqlite3
import pandas as pd
from pandas import DataFrame, Series
import numpy as np

# list of working days
days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


'''
    steps to use the database handler:
    1. call make_database() once to create the database and the timetable table
'''

# database work and stuff
def make_database():
    '''
    Docstring for making the database and the timetable table
    it only creates the table if it does not already exist but doesnt populate it
    '''
    conn = sqlite3.connect('uni_timetable.db')
    crsr = conn.cursor()

    crsr.execute('''CREATE TABLE IF NOT EXISTS timetable (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                DAY TEXT NOT NULL,
                START_TIME TEXT NOT NULL,
                END_TIME TEXT NOT NULL,
                SUBJECT TEXT NOT NULL,
                CLASSROOM TEXT NOT NULL,
                SECTION TEXT NOT NULL,

                UNIQUE(DAY, CLASSROOM, START_TIME) -- to avoid overlapping classes in the same classroom just in case the timetable is incorrect
                )
                ''')

    crsr.execute(''' CREATE INDEX IF NOT EXISTS idx_day_section ON timetable (DAY, SECTION) ''')
    conn.commit()
    conn.close()


def insert_timetable(df: DataFrame):
    '''
    Docstring for insert_timetable

    :param df: DataFrame containing the timetable data to be inserted into the database
    :type df: DataFrame

    returns: None

    Explanation:
    the function takes in a reference to a pandas DataFrame containing the timetable data and inserts it into the timetable table in the database. the DataFrame is expected to have the following columns: DAY, START_TIME, END_TIME, SUBJECT, CLASSROOM, SECTION.
    '''
    conn = sqlite3.connect('uni_timetable.db')
    crsr = conn.cursor()

