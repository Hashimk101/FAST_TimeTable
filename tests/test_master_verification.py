import unittest
import sqlite3
import re
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import databaseHandler
import sync_faculty_to_supabase as sfs

class TestStudentPipeline(unittest.TestCase):
    def setUp(self):
        self.theory_conn = sqlite3.connect('uni_timetable.db')
        self.theory_cur = self.theory_conn.cursor()
        self.lab_conn = sqlite3.connect('uni_timetable_lab.db')
        self.lab_cur = self.lab_conn.cursor()

    def tearDown(self):
        self.theory_conn.close()
        self.lab_conn.close()

    def test_v01_exploded_sections_ai_a(self):
        """V-01: Exploded section AI-A should have OOP on Monday and Friday."""
        rows = self.theory_cur.execute(
            "SELECT DAY, START_TIME, END_TIME, SUBJECT, CLASSROOM FROM timetable WHERE SECTION = 'AI-A' AND SUBJECT = 'OOP'"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        days = {r[0] for r in rows}
        self.assertIn('Monday', days)
        self.assertIn('Friday', days)

    def test_v02_exploded_sections_cs_a(self):
        """V-02: Exploded section CS-A should have Digital Sustain and PF Tutorial."""
        rows_ds = self.theory_cur.execute(
            "SELECT DAY, START_TIME, SUBJECT, CLASSROOM FROM timetable WHERE SECTION = 'CS-A' AND SUBJECT = 'Digital Sustain'"
        ).fetchall()
        self.assertGreaterEqual(len(rows_ds), 2)

        rows_tut = self.theory_cur.execute(
            "SELECT DAY, START_TIME, SUBJECT, STATUS FROM timetable WHERE SECTION = 'CS-A' AND STATUS = 'Tutorial'"
        ).fetchall()
        self.assertGreaterEqual(len(rows_tut), 1)

    def test_v03_exploded_sections_lab(self):
        """V-03: Exploded section AI-A should have COAL Lab and OOP Lab."""
        rows_coal = self.lab_cur.execute(
            "SELECT DAY, START_TIME, SUBJECT, LAB FROM timetable WHERE SECTION = 'AI-A' AND SUBJECT = 'COAL Lab'"
        ).fetchall()
        self.assertGreaterEqual(len(rows_coal), 1)

        rows_oop = self.lab_cur.execute(
            "SELECT DAY, START_TIME, SUBJECT, LAB FROM timetable WHERE SECTION = 'AI-A' AND SUBJECT = 'OOP Lab'"
        ).fetchall()
        self.assertGreaterEqual(len(rows_oop), 1)

    def test_v07_no_corrupt_timeslots(self):
        """V-07: Ensure no corrupt timeslots with brackets or trailing notes."""
        corrupt_theory = self.theory_cur.execute(
            "SELECT * FROM timetable WHERE START_TIME LIKE '%(%' OR END_TIME LIKE '%)%'"
        ).fetchall()
        self.assertEqual(len(corrupt_theory), 0)

        corrupt_lab = self.lab_cur.execute(
            "SELECT * FROM timetable WHERE START_TIME LIKE '%(%' OR END_TIME LIKE '%)%'"
        ).fetchall()
        self.assertEqual(len(corrupt_lab), 0)

    def test_v08_tutorial_status_preservation(self):
        """V-08: Ensure tutorial cells have STATUS = 'Tutorial'."""
        tut_rows = self.theory_cur.execute(
            "SELECT DAY, START_TIME, SUBJECT, SECTION, STATUS FROM timetable WHERE STATUS = 'Tutorial'"
        ).fetchall()
        self.assertGreaterEqual(len(tut_rows), 10)
        for r in tut_rows:
            self.assertEqual(r[4], 'Tutorial')
            self.assertNotIn('Tutorial', r[3])

    def test_decoy_room_suppression(self):
        """Ensure Tuesday 11:30 C-110 pointer cell is omitted in favor of actual C-301 room."""
        c110_slots = self.theory_cur.execute(
            "SELECT * FROM timetable WHERE DAY = 'Tuesday' AND START_TIME = '11:30' AND CLASSROOM = 'C-110'"
        ).fetchall()
        self.assertEqual(len(c110_slots), 0)

        c301_slots = self.theory_cur.execute(
            "SELECT * FROM timetable WHERE DAY = 'Tuesday' AND START_TIME = '11:30' AND CLASSROOM = 'C-301'"
        ).fetchall()
        self.assertEqual(len(c301_slots), 1)

    def test_fetch_timetable_for_section(self):
        """Verify students can retrieve full schedules for exploded sections."""
        sched = databaseHandler.fetch_timetable_for_section('uni_timetable.db', 'AI-A', ['OOP'])
        monday_classes = sched[0]
        friday_classes = sched[4]
        self.assertTrue(any(c.subject == 'OOP' for c in monday_classes))
        self.assertTrue(any(c.subject == 'OOP' for c in friday_classes))


class TestFacultySyncPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allocations = sfs.read_course_allocations()
        cls.faculty_roster = sfs.decode_faculty_bin()
        cls.records = sfs.compile_faculty_schedules(cls.allocations, cls.faculty_roster)
        cls.record_map = {r['email']: r for r in cls.records}

    def test_v04_noor_ul_ain_disambiguation(self):
        """V-04: Disambiguate Ms. Noor Ul Ain between CS theory and SE lab."""
        noor_cs = self.record_map.get('noorul.ain@nu.edu.pk')
        self.assertIsNotNone(noor_cs)
        self.assertEqual(noor_cs['department'], 'Computer Science')
        cs_slots = [s for day in noor_cs['schedule'].values() for s in day]
        self.assertGreaterEqual(len(cs_slots), 6)
        self.assertTrue(all(not s['is_lab'] for s in cs_slots))

        noor_se = self.record_map.get('noor.ulain@isb.nu.edu.pk')
        self.assertIsNotNone(noor_se)
        self.assertEqual(noor_se['department'], 'Software Engineering')
        se_slots = [s for day in noor_se['schedule'].values() for s in day]
        self.assertGreaterEqual(len(se_slots), 3)
        self.assertTrue(all(s['is_lab'] for s in se_slots))

    def test_v05_usama_bin_imran_isolation(self):
        """V-05: Usama Bin Imran should have 0 stolen theory slots and clean section badges."""
        usama = self.record_map.get('usama.imran@isb.nu.edu.pk')
        self.assertIsNotNone(usama)
        slots = [(day, s) for day, day_slots in usama['schedule'].items() for s in day_slots]
        self.assertEqual(len(slots), 3)
        # All slots must be labs
        self.assertTrue(all(s['is_lab'] for _, s in slots))
        # Zero theory COAL slots on Monday/Wednesday
        for day, s in slots:
            self.assertNotEqual((day, s['start_time']), ('Monday', '03:55'))
            self.assertNotEqual((day, s['start_time']), ('Wednesday', '03:55'))
        # Section on Friday afternoon should be clean (not raw slashed)
        fri_lab = [s for day, s in slots if day == 'Friday' and s['start_time'] == '02:30'][0]
        self.assertEqual(fri_lab['section'], 'AI-A, CS-A')

    def test_v06_aqib_rehman_retention(self):
        """V-06: Aqib Rehman retains Monday and Wednesday 03:55 PM COAL CS-B theory lectures."""
        aqib = self.record_map.get('aqib.rehman@isb.nu.edu.pk')
        self.assertIsNotNone(aqib)
        slots = [(day, s) for day, day_slots in aqib['schedule'].items() for s in day_slots]
        mon_slot = [s for day, s in slots if day == 'Monday' and s['start_time'] == '03:55']
        wed_slot = [s for day, s in slots if day == 'Wednesday' and s['start_time'] == '03:55']
        self.assertEqual(len(mon_slot), 1)
        self.assertEqual(len(wed_slot), 1)
        self.assertEqual(mon_slot[0]['subject'], 'COAL')
        self.assertEqual(wed_slot[0]['subject'], 'COAL')

    def test_canonical_mappings(self):
        """Verify canonical mappings for Ali Hamza, Faisal Cheema, and Zafar Iqbal."""
        ali = [r for r in self.records if 'ali hamza' in r['name'].lower()][0]
        ali_slots = [s for day in ali['schedule'].values() for s in day]
        self.assertTrue(any('Prog for AI Lab' in s['subject'] for s in ali_slots))

        faisal = [r for r in self.records if 'faisal cheema' in r['name'].lower()][0]
        faisal_subs = {s['subject'] for day in faisal['schedule'].values() for s in day}
        self.assertIn('Fund of Data Vis', faisal_subs)

        zafar = [r for r in self.records if 'zafar iqbal' in r['name'].lower()][0]
        zafar_subs = {s['subject'] for day in zafar['schedule'].values() for s in day}
        self.assertIn('Security Ops', zafar_subs)

if __name__ == '__main__':
    unittest.main()
