#!/usr/bin/env python3
"""
tests/test_reconciliation_auditor_edge_cases.py

Comprehensive Edge-Case Test Suite for FAST Faculty Timetable Reconciliation & Audit Engine.
Tests all discrepancy scenarios, fuzzy typo suggestions, independent study categorization,
orphaned room slot severity differentiation, malformed inputs, and export formatting.
"""

import os
import sys
import csv
import json
import sqlite3
import tempfile
import unittest

# Ensure parent directory is on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

import sync_faculty_to_supabase as sfs


class TestReconciliationAuditorEdgeCases(unittest.TestCase):
    """Rigorous unit test suite testing all edge cases of ReconciliationAuditor."""

    def setUp(self):
        """Create fresh in-memory SQLite theory and lab databases for each test."""
        self.conn_theory = sqlite3.connect(":memory:")
        self.conn_theory.row_factory = sqlite3.Row
        self.cur_theory = self.conn_theory.cursor()
        self.cur_theory.execute("""
            CREATE TABLE timetable (
                ID INTEGER PRIMARY KEY,
                DAY TEXT,
                START_TIME TEXT,
                END_TIME TEXT,
                SUBJECT TEXT,
                CLASSROOM TEXT,
                SECTION TEXT,
                BATCH TEXT,
                STATUS TEXT
            )
        """)

        self.conn_lab = sqlite3.connect(":memory:")
        self.conn_lab.row_factory = sqlite3.Row
        self.cur_lab = self.conn_lab.cursor()
        self.cur_lab.execute("""
            CREATE TABLE timetable (
                ID INTEGER PRIMARY KEY,
                DAY TEXT,
                START_TIME TEXT,
                END_TIME TEXT,
                SUBJECT TEXT,
                LAB TEXT,
                SECTION TEXT,
                BATCH TEXT,
                STATUS TEXT
            )
        """)

        self.auditor = sfs.ReconciliationAuditor(semester_id="2027-spring-test")

    def tearDown(self):
        self.conn_theory.close()
        self.conn_lab.close()

    def test_01_fuzzy_typo_near_miss_suggestion(self):
        """Edge Case 1: Fuzzy Levenshtein match (>= 50%) suggests likely typo in subject name."""
        self.cur_theory.execute("""
            INSERT INTO timetable (ID, DAY, START_TIME, END_TIME, SUBJECT, CLASSROOM, SECTION, BATCH, STATUS)
            VALUES (1, 'Monday', '08:30', '09:50', 'O.O.P', 'C-301', 'CS-A', 'BS 26 CS', 'Regular')
        """)

        alloc = {
            "course_code": "CS2001",
            "course_title": "Object Oriented Programming",
            "canonical_subject": "OOP",
            "batch": "BS 26 CS",
            "timetable_section": "CS-A",
            "is_lab": False,
            "sheet": "Computing-Theory"
        }
        self.auditor.record_allocation_unmatched(alloc, {"name": "Dr. Test"}, "test@nu.edu.pk", self.cur_theory, self.cur_lab)

        self.assertEqual(len(self.auditor.unmatched_allocations), 1)
        entry = self.auditor.unmatched_allocations[0]
        self.assertEqual(entry["severity"], "WARNING")
        self.assertIn("O.O.P", entry["suggested_action"])
        self.assertIn("similarity", entry["suggested_action"].lower())
        self.assertIn("CANONICAL_SUBJECT_MAP", entry["suggested_action"])

    def test_02_distant_mismatch_no_false_positive_typo(self):
        """Edge Case 2: Subject similarity < 50% does not trigger a false-positive typo suggestion."""
        self.cur_theory.execute("""
            INSERT INTO timetable (ID, DAY, START_TIME, END_TIME, SUBJECT, CLASSROOM, SECTION, BATCH, STATUS)
            VALUES (1, 'Monday', '08:30', '09:50', 'Differential Equations', 'C-301', 'CS-A', 'BS 26 CS', 'Regular')
        """)

        alloc = {
            "course_code": "CS2001",
            "course_title": "Object Oriented Programming",
            "canonical_subject": "OOP",
            "batch": "BS 26 CS",
            "timetable_section": "CS-A",
            "is_lab": False,
            "sheet": "Computing-Theory"
        }
        self.auditor.record_allocation_unmatched(alloc, {"name": "Dr. Test"}, "test@nu.edu.pk", self.cur_theory, self.cur_lab)

        entry = self.auditor.unmatched_allocations[0]
        self.assertEqual(entry["severity"], "WARNING")
        # Should not falsely suggest 'Differential Equations' for 'OOP'
        self.assertNotIn("Differential Equations", entry["suggested_action"])
        self.assertIn("Verify if section was scheduled", entry["suggested_action"])

    def test_03_research_and_thesis_severity_info(self):
        """Edge Case 3: FYP, MS Thesis, and independent study courses are classified as severity INFO, not WARNING."""
        research_titles = [
            ("CY4091", "Final Year Project-I (CY)", "FYPI"),
            ("SE4092", "Final Year Project-II", "FYPII"),
            ("CS5091", "MS Thesis - 1", "MT1"),
            ("CS6092", "PhD Thesis - 2", "PT2"),
            ("CS4090", "Project-I (Senior Design)", "PROJ")
        ]

        for code, title, canon in research_titles:
            alloc = {
                "course_code": code,
                "course_title": title,
                "canonical_subject": canon,
                "batch": "BS 23 CS",
                "timetable_section": "CS-A",
                "is_lab": False,
                "sheet": "Computing-Theory"
            }
            self.auditor.record_allocation_unmatched(alloc, {"name": "Advisor"}, "advisor@nu.edu.pk", self.cur_theory, self.cur_lab)

        self.assertEqual(len(self.auditor.unmatched_allocations), 5)
        for entry in self.auditor.unmatched_allocations:
            self.assertEqual(entry["severity"], "INFO", f"Failed for {entry['course_title']}")
            self.assertIn("independent study", entry["details"].lower())
            self.assertEqual(entry["suggested_action"], "")

    def test_04_regular_lecture_missing_severity_warning(self):
        """Edge Case 4: Real scheduled lecture courses missing from timetable receive WARNING."""
        alloc = {
            "course_code": "CS3005",
            "course_title": "Theory of Automata",
            "canonical_subject": "Automata",
            "batch": "BS 24 CS",
            "timetable_section": "CS-A",
            "is_lab": False,
            "sheet": "Computing-Theory"
        }
        self.auditor.record_allocation_unmatched(alloc, {"name": "Dr. Automata"}, "auto@nu.edu.pk", self.cur_theory, self.cur_lab)

        entry = self.auditor.unmatched_allocations[0]
        self.assertEqual(entry["severity"], "WARNING")
        self.assertIn("No timetable slots found", entry["details"])

    def test_05_orphaned_slots_active_vs_cancelled_severity(self):
        """Edge Case 5: Active orphaned slots receive MEDIUM severity; cancelled slots receive INFO severity."""
        self.cur_theory.execute("""
            INSERT INTO timetable (ID, DAY, START_TIME, END_TIME, SUBJECT, CLASSROOM, SECTION, BATCH, STATUS)
            VALUES 
                (1, 'Monday', '08:30', '09:50', 'Calculus', 'C-301', 'CS-A', 'BS 26 CS', 'Regular'),
                (2, 'Tuesday', '10:00', '11:20', 'Physics', 'C-302', 'CS-B', 'BS 26 CS', 'Cancelled')
        """)

        # Claim slot 1 but leave slot 2 unclaimed
        # In this test, leave both unclaimed to test both severities
        self.auditor.finalize(self.cur_theory, self.cur_lab, "2027-spring-test")

        self.assertEqual(len(self.auditor.orphaned_slots), 2)
        regular_orphan = next(o for o in self.auditor.orphaned_slots if o["subject"] == "Calculus")
        cancelled_orphan = next(o for o in self.auditor.orphaned_slots if o["subject"] == "Physics")

        self.assertEqual(regular_orphan["severity"], "MEDIUM")
        self.assertEqual(cancelled_orphan["severity"], "INFO")

    def test_06_claimed_slots_properly_excluded_from_orphans(self):
        """Edge Case 6: Slots claimed by allocations are excluded from orphaned list."""
        self.cur_theory.execute("""
            INSERT INTO timetable (ID, DAY, START_TIME, END_TIME, SUBJECT, CLASSROOM, SECTION, BATCH, STATUS)
            VALUES 
                (101, 'Wednesday', '08:30', '09:50', 'Data Structures', 'C-301', 'CS-A', 'BS 25 CS', 'Regular'),
                (102, 'Thursday', '10:00', '11:20', 'Database Systems', 'C-302', 'CS-B', 'BS 25 CS', 'Regular')
        """)

        # Mark slot 101 as claimed (theory is is_lab=False)
        self.auditor.record_claimed_slot(is_lab=False, rowid=101)
        self.auditor.finalize(self.cur_theory, self.cur_lab, "2027-spring-test")

        self.assertEqual(self.auditor.total_db_slots, 2)
        self.assertEqual(self.auditor.claimed_db_slots_count, 1)
        self.assertEqual(len(self.auditor.orphaned_slots), 1)
        self.assertEqual(self.auditor.orphaned_slots[0]["subject"], "Database Systems")

    def test_07_visiting_faculty_synthetic_account_logging(self):
        """Edge Case 7: Visiting instructors are tracked and sampled in the audit summary."""
        external_instructors = {
            "Dr. Guest Lecturer",
            "Engr. Visiting Specialist",
            "Ms. Industry Expert"
        }
        self.auditor.record_unmatched_instructors(external_instructors)

        summary = self.auditor.get_summary_dict()
        self.assertEqual(summary["metrics"]["visiting_faculty_count"], 3)
        self.assertEqual(sorted(summary["visiting_faculty_sample"]), sorted(list(external_instructors)))

    def test_08_zero_division_and_empty_dataset_resilience(self):
        """Edge Case 8: Auditor handles zero allocations and empty databases without ZeroDivisionError."""
        self.auditor.finalize(self.cur_theory, self.cur_lab, "2027-empty")

        summary = self.auditor.get_summary_dict()
        self.assertEqual(summary["metrics"]["total_allocations"], 0)
        self.assertEqual(summary["metrics"]["allocation_match_rate_pct"], 0.0)
        self.assertEqual(summary["metrics"]["total_timetable_slots"], 0)
        self.assertEqual(summary["metrics"]["timetable_coverage_pct"], 0.0)

        # Ensure printing and exports don't crash
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "empty_audit.csv")
            json_path = os.path.join(tmpdir, "empty_audit.json")
            self.auditor.export_csv(csv_path)
            self.auditor.export_json(json_path)
            self.assertTrue(os.path.exists(csv_path))
            self.assertTrue(os.path.exists(json_path))

    def test_09_null_and_malformed_fields_tolerance(self):
        """Edge Case 9: None/null values in allocations and timetable rows don't cause AttributeError or TypeError."""
        self.cur_theory.execute("""
            INSERT INTO timetable (ID, DAY, START_TIME, END_TIME, SUBJECT, CLASSROOM, SECTION, BATCH, STATUS)
            VALUES (999, 'Friday', NULL, NULL, NULL, NULL, NULL, NULL, NULL)
        """)

        alloc_malformed = {
            "course_code": None,
            "course_title": None,
            "canonical_subject": None,
            "batch": None,
            "timetable_section": None,
            "is_lab": False,
            "sheet": None
        }

        # Should execute cleanly without raising exceptions
        self.auditor.record_allocation_unmatched(alloc_malformed, {}, "", self.cur_theory, self.cur_lab)
        self.auditor.finalize(self.cur_theory, self.cur_lab, "2027-spring-test")

        summary = self.auditor.get_summary_dict()
        self.assertEqual(summary["metrics"]["unmatched_allocations"], 1)
        self.assertEqual(summary["metrics"]["orphaned_slots"], 1)

    def test_10_csv_and_json_export_compliance(self):
        """Edge Case 10: Special characters, commas, and quotes in titles are properly formatted in CSV and JSON."""
        alloc = {
            "course_code": "HU1001",
            "course_title": 'Islamic Studies & "Ethics", Society',
            "canonical_subject": "Isl & Ethics",
            "batch": "BS 26 CS",
            "timetable_section": "CS-A, CS-B",
            "is_lab": False,
            "sheet": "S&H"
        }
        self.auditor.record_allocation_unmatched(alloc, {"name": 'Dr. O\'Connor, PhD'}, "oconnor@nu.edu.pk", self.cur_theory, self.cur_lab)

        self.cur_theory.execute("""
            INSERT INTO timetable (ID, DAY, START_TIME, END_TIME, SUBJECT, CLASSROOM, SECTION, BATCH, STATUS)
            VALUES (888, 'Monday', '10:00', '11:20', 'Adv "Topics", AI', 'Lab-1, New Wing', 'A, B', 'Batch 2025', 'Regular')
        """)
        self.auditor.finalize(self.cur_theory, self.cur_lab, "2027-spring-test")

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test_export.csv")
            json_path = os.path.join(tmpdir, "test_export.json")
            self.auditor.export_csv(csv_path)
            self.auditor.export_json(json_path)

            # Read back CSV using standard csv.reader to verify column counts are intact
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                self.assertEqual(len(header), 16)
                for row in reader:
                    self.assertEqual(len(row), 16, f"Row column count corrupted: {row}")

            # Read back JSON
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertIn("metrics", data)
                self.assertEqual(data["metrics"]["unmatched_allocations"], 1)
                self.assertEqual(data["metrics"]["orphaned_slots"], 1)

    def test_11_mathematical_consistency_audit_invariants(self):
        """Edge Case 11: Invariant check - total_slots == claimed + orphaned, total_alloc == matched + unmatched."""
        self.cur_theory.execute("""
            INSERT INTO timetable (ID, DAY, START_TIME, END_TIME, SUBJECT, CLASSROOM, SECTION, BATCH, STATUS)
            VALUES 
                (1, 'Monday', '08:30', '09:50', 'Sub1', 'C-301', 'A', 'B1', 'Regular'),
                (2, 'Tuesday', '10:00', '11:20', 'Sub2', 'C-302', 'B', 'B1', 'Regular'),
                (3, 'Wednesday', '11:30', '12:50', 'Sub3', 'C-303', 'C', 'B1', 'Regular')
        """)

        # Claim slot 1 and 2
        self.auditor.record_claimed_slot(False, 1)
        self.auditor.record_claimed_slot(False, 2)

        # 3 allocations: 2 matched, 1 unmatched
        alloc_m1 = {"course_code": "C1", "canonical_subject": "S1"}
        alloc_m2 = {"course_code": "C2", "canonical_subject": "S2"}
        alloc_u = {"course_code": "C3", "canonical_subject": "S3"}

        self.auditor.record_allocation_matched(alloc_m1, {}, "m1@nu.edu.pk", [{}], False)
        self.auditor.record_allocation_matched(alloc_m2, {}, "m2@nu.edu.pk", [{}], False)
        self.auditor.record_allocation_unmatched(alloc_u, {}, "u@nu.edu.pk", self.cur_theory, self.cur_lab)

        self.auditor.finalize(self.cur_theory, self.cur_lab, "2027-spring-test")
        summary = self.auditor.get_summary_dict()["metrics"]

        # Invariant 1: Total allocations = matched + unmatched
        self.assertEqual(summary["total_allocations"], summary["matched_allocations"] + summary["unmatched_allocations"])
        self.assertEqual(summary["total_allocations"], 3)
        self.assertEqual(summary["matched_allocations"], 2)
        self.assertEqual(summary["unmatched_allocations"], 1)

        # Invariant 2: Total timetable slots = claimed + orphaned
        self.assertEqual(summary["total_timetable_slots"], summary["claimed_slots"] + summary["orphaned_slots"])
        self.assertEqual(summary["total_timetable_slots"], 3)
        self.assertEqual(summary["claimed_slots"], 2)
        self.assertEqual(summary["orphaned_slots"], 1)


if __name__ == "__main__":
    unittest.main()
