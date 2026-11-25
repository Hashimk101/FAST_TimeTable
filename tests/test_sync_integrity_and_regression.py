import os
import sys
import sqlite3
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import sync_faculty_to_supabase as sync_mod


class TestSyncIntegrityAndRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.theory_db = os.path.join(ROOT_DIR, "uni_timetable.db")
        cls.lab_db = os.path.join(ROOT_DIR, "uni_timetable_lab.db")
        cls.excel_path = os.path.join(ROOT_DIR, sync_mod.DEFAULT_EXCEL_PATH)
        cls.faculty_bin = os.path.join(ROOT_DIR, sync_mod.FACULTY_BIN_PATH)

        cls.roster = sync_mod.decode_faculty_bin(cls.faculty_bin)
        cls.allocs = sync_mod.read_course_allocations(cls.excel_path, year=2026, season="fall")
        cls.records = sync_mod.compile_faculty_schedules(
            cls.allocs,
            cls.roster,
            theory_db=cls.theory_db,
            lab_db=cls.lab_db,
            semester_id="2026-fall",
            audit_csv_path=None,
            audit_json_path=None,
        )
        cls.by_email = {r["email"].lower(): r for r in cls.records}

    def test_01_full_compile_zero_missing_course_anomalies(self):
        """Every non-FYP/Thesis course across 227 faculty compiles to >= 1 timetable slot."""
        anomalies = sync_mod.verify_compiled_records_integrity(self.records)
        self.assertEqual(anomalies, [], f"Unexpected 0-slot anomalies: {anomalies}")

    def test_02_nayab_issue_1_dr_hina_ayaz_has_spm(self):
        """Issue 1: Dr. Hina Ayaz includes Fund of SPM alongside Info Sec."""
        rec = self.by_email["hina.ayaz@isb.nu.edu.pk"]
        slots = [s for d in sync_mod.DAYS_OF_WEEK for s in rec["schedule"][d]]
        subjects = {s["subject"] for s in slots}
        self.assertIn("Info Sec", subjects)
        self.assertIn("Fund of SPM", subjects)
        spm_slots = [s for s in slots if s["subject"] == "Fund of SPM"]
        self.assertGreaterEqual(len(spm_slots), 2)

    def test_03_nayab_issue_2_noor_ul_ain_strict_department_split(self):
        """Issue 2: CS and SE Noor ul Ain remain strictly isolated by email & course."""
        cs_rec = self.by_email["noorul.ain@nu.edu.pk"]
        se_rec = self.by_email["noor.ulain@isb.nu.edu.pk"]

        cs_subjs = {s["subject"] for d in sync_mod.DAYS_OF_WEEK for s in cs_rec["schedule"][d]}
        se_subjs = {s["subject"] for d in sync_mod.DAYS_OF_WEEK for s in se_rec["schedule"][d]}

        self.assertEqual(cs_subjs, {"Comp Arch"})
        self.assertEqual(se_subjs, {"AI Lab"})

    def test_04_nayab_issue_3_nirmal_tariq_tutorials_tagged(self):
        """Issue 3: Ms. Nirmal Tariq's 3 extra PF sessions are explicitly tagged status='Tutorial'."""
        rec = self.by_email["nirmal.tariq@nu.edu.pk"]
        slots = [s for d in sync_mod.DAYS_OF_WEEK for s in rec["schedule"][d]]
        regular = [s for s in slots if not s.get("status")]
        tutorials = [s for s in slots if s.get("status") == "Tutorial"]
        self.assertEqual(len(regular), 6)
        self.assertEqual(len(tutorials), 3)

    def test_05_nayab_issue_4_saad_salman_algo_clean_and_smd_present(self):
        """Issue 4: Mr. Saad Salman has 4 regular Algo slots (no extra Wed Resch) AND includes SMD."""
        rec = self.by_email["saad.salman@nu.edu.pk"]
        slots = [s for d in sync_mod.DAYS_OF_WEEK for s in rec["schedule"][d]]
        algo_slots = [s for s in slots if s["subject"] == "Algo"]
        smd_slots = [s for s in slots if "SMD" in s["subject"]]

        self.assertEqual(len(algo_slots), 4)
        self.assertTrue(all(s.get("status") is None for s in algo_slots))
        self.assertGreaterEqual(len(smd_slots), 2)

    def test_06_continuous_sync_self_heals_courses_missing_from_schedule(self):
        """
        Regression guard: Simulate legacy Supabase rows where `Fund of SPM` and `SMD`
        exist in `courses` (without `allocations`) while `schedule` omits them completely.
        `reconcile_existing_db_rows` must recover them automatically without Excel.
        """
        hina_real = self.by_email["hina.ayaz@isb.nu.edu.pk"]
        saad_real = self.by_email["saad.salman@nu.edu.pk"]

        legacy_rows = [
            {
                "email": hina_real["email"],
                "semester_id": "2026-fall",
                "name": hina_real["name"],
                "designation": hina_real["designation"],
                "department": hina_real["department"],
                "office": hina_real["office"],
                # Corrupt/stale schedule missing Fund of SPM slots, plus a custom meeting!
                "schedule": {
                    "Monday": [],
                    "Tuesday": [s for s in hina_real["schedule"]["Tuesday"] if s["subject"] == "Info Sec"],
                    "Wednesday": [],
                    "Thursday": [s for s in hina_real["schedule"]["Thursday"] if s["subject"] == "Info Sec"],
                    "Friday": [
                        {
                            "id": "act-123",
                            "subject": "Office Hours",
                            "start_time": "02:00",
                            "end_time": "03:00",
                            "isCustom": True,
                            "customCategory": "office_hours",
                        }
                    ],
                    "Saturday": [],
                    "custom_activities": [{"id": "act-123", "title": "Office Hours"}],
                },
                # Legacy courses payload lacking `allocations`
                "courses": [
                    {k: v for k, v in c.items() if k != "allocations"}
                    for c in hina_real["courses"]
                ],
                "total_credit_hours": 6.0,
            },
            {
                "email": saad_real["email"],
                "semester_id": "2026-fall",
                "name": saad_real["name"],
                "designation": saad_real["designation"],
                "department": saad_real["department"],
                "office": saad_real["office"],
                # Corrupt/stale schedule missing SMD slots completely
                "schedule": {
                    "Monday": [],
                    "Tuesday": [s for s in saad_real["schedule"]["Tuesday"] if s["subject"] == "Algo"],
                    "Wednesday": [],
                    "Thursday": [s for s in saad_real["schedule"]["Thursday"] if s["subject"] == "Algo"],
                    "Friday": [],
                    "Saturday": [],
                },
                "courses": [
                    {k: v for k, v in c.items() if k != "allocations"}
                    for c in saad_real["courses"]
                ],
                "total_credit_hours": 6.0,
            },
        ]

        conn_t = sqlite3.connect(self.theory_db)
        conn_t.row_factory = sqlite3.Row
        conn_l = sqlite3.connect(self.lab_db)
        conn_l.row_factory = sqlite3.Row
        try:
            reconciled = sync_mod.reconcile_existing_db_rows(
                legacy_rows, conn_t.cursor(), conn_l.cursor(), semester_id="2026-fall"
            )
        finally:
            conn_t.close()
            conn_l.close()

        reconciled_by_email = {r["email"]: r for r in reconciled}

        hina_healed = reconciled_by_email[hina_real["email"]]
        hina_subjs = {s["subject"] for d in sync_mod.DAYS_OF_WEEK for s in hina_healed["schedule"][d]}
        self.assertIn("Fund of SPM", hina_subjs)
        self.assertIn("Office Hours", hina_subjs)
        self.assertIn("custom_activities", hina_healed["schedule"])

        saad_healed = reconciled_by_email[saad_real["email"]]
        saad_subjs = {s["subject"] for d in sync_mod.DAYS_OF_WEEK for s in saad_healed["schedule"][d]}
        self.assertTrue(any("SMD" in subj for subj in saad_subjs))

    def test_07_short_acronym_boundary_guard(self):
        """Short acronyms (<= 3 chars) match SMD Nov 27 while never matching 'Data St Lab' for 'LA'."""
        conn_t = sqlite3.connect(self.theory_db)
        conn_t.row_factory = sqlite3.Row
        conn_l = sqlite3.connect(self.lab_db)
        conn_l.row_factory = sqlite3.Row
        try:
            la_rows, _ = sync_mod._query_timetable_slots(
                conn_t.cursor(), conn_l.cursor(), "", "", "LA", False
            )
            self.assertTrue(all("lab" not in r["SUBJECT"].lower() for r in la_rows))

            smd_rows, _ = sync_mod._query_timetable_slots(
                conn_t.cursor(), conn_l.cursor(), "BS 23 CS", "CS-A", "SMD", False
            )
            self.assertTrue(any(r["SUBJECT"] == "SMD" for r in smd_rows))
        finally:
            conn_t.close()
            conn_l.close()


if __name__ == "__main__":
    unittest.main()
