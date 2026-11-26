#!/usr/bin/env python3
"""
tests/test_v2_3_upgrades.py

Comprehensive unit tests covering all 5 Upstream Integration Directive v2.3 upgrades:
1. Centralized active semester & spreadsheet config (`config.py`) + call-time resolution.
2. Deterministic 12-char `slot_uid`, strict Layer 1 purity, anchored paths, `/tmp/` isolation,
   zip-bomb rejection, `--mode {draft,refresh-draft,sync,reconcile-snapshot,excel}`, and job safety.
3. Hybrid rollback re-reconcile, continuous sync TOCTOU / sync_policy guards, `MAX(version)+1` floor.
4. Reader hardening (`RefreshError`, empty `data`, `429/500/503` backoff, `rebuild_db` fail-loud,
   stale `.bin` cleanup in `generate_static_json.py`, HMAC wire contract, `sync.yml` structure).
5. `standalone_apps_script.js` authenticated fail-closed watcher & dual value/color MD5 hashing.
"""

import hashlib
import hmac
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import ExitStack, closing
from pathlib import Path
from unittest import mock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
import databaseHandler
import generate_static_json
import main as main_mod
import rebuild_db
import rebuild_subjects
import sheets_subject_extractor
import sheets_to_df
import sync_faculty_to_supabase as sfs
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError


class FakeCursor:
    """Flexible scripted cursor mock for psycopg2 unit tests."""

    def __init__(self, handler):
        self.handler = handler
        self.queries = []
        self._results = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        sql_clean = " ".join(str(sql).split())
        self.queries.append((sql_clean, params))
        res = self.handler("execute", sql_clean, params, self)
        self._results = res if isinstance(res, list) else []

    def fetchone(self):
        return self._results[0] if self._results else None

    def fetchall(self):
        return list(self._results)

    def close(self):
        pass


class FakeConn:
    def __init__(self, handler):
        self.handler = handler
        self.autocommit = False
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.cursor_obj = FakeCursor(handler)

    def cursor(self, cursor_factory=None):
        return self.cursor_obj

    def commit(self):
        self.committed = True
        self.handler("commit", "", None, self.cursor_obj)

    def rollback(self):
        self.rolled_back = True
        self.handler("rollback", "", None, self.cursor_obj)

    def close(self):
        self.closed = True


def make_http_error(status_code: int, message: str = "API error"):
    resp = mock.MagicMock()
    resp.status = status_code
    resp.reason = message
    return HttpError(resp=resp, content=message.encode("utf-8"))


class TestUpgrade1Config(unittest.TestCase):
    def test_explicit_override_valid_and_invalid(self):
        valid_id = "1vlTuotLw34fedME3gNQj09cZw-todVomxAiu5P1wZ6Q"
        cfg = config.get_active_semester_config(override_id=valid_id)
        self.assertEqual(cfg["google_sheet_id"], valid_id)
        self.assertIsNone(cfg["semester_id"])

        sem_id, sheet_id = config.get_active_spreadsheet_id(override_id=valid_id)
        self.assertIsNone(sem_id)
        self.assertEqual(sheet_id, valid_id)

        for bad in ("", "too-short", "bad$chars!" * 4, "x" * 129):
            with self.assertRaises(ValueError):
                config.get_active_semester_config(override_id=bad)

    def test_authoritative_supabase_query(self):
        captured = {}

        def handler(op, sql, params, cur):
            if op == "execute":
                captured["sql"] = sql
                return [(
                    "2027-spring",
                    "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD",
                    2027,
                    "Spring",
                    "AUTO_ENABLED",
                    7,
                )]
            return []

        fake_conn = FakeConn(handler)
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake", "CI": "true"}, clear=False):
            with mock.patch.object(config.psycopg2, "connect", return_value=fake_conn):
                cfg = config.get_active_semester_config()
                sem_id, sheet_id = config.get_active_spreadsheet_id()

        self.assertIn("is_active = true AND is_published = true AND deleted_at IS NULL", captured["sql"])
        self.assertEqual(cfg["semester_id"], "2027-spring")
        self.assertEqual(cfg["academic_year"], 2027)
        self.assertEqual(cfg["season"], "Spring")
        self.assertEqual(cfg["sync_policy"], "AUTO_ENABLED")
        self.assertEqual(cfg["state_version"], 7)
        self.assertEqual((sem_id, sheet_id), ("2027-spring", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"))

    def test_local_dotenv_fallback_allowed_when_not_ci(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_file = Path(tmpdir) / ".env"
            dotenv_file.write_text("SPREADSHEET_ID='1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD'\n", encoding="utf-8")

            env_patch = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "CI", "SPREADSHEET_ID")}
            with mock.patch.dict(os.environ, env_patch, clear=True):
                cfg = config.get_active_semester_config(dotenv_path=dotenv_file)

        self.assertIsNone(cfg["semester_id"])
        self.assertEqual(cfg["google_sheet_id"], "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD")

    def test_ci_true_fails_closed_without_database_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_file = Path(tmpdir) / ".env"
            dotenv_file.write_text(
                "DATABASE_URL=postgresql://local\nSPREADSHEET_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD\n",
                encoding="utf-8",
            )
            env_patch = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "SPREADSHEET_ID")}
            env_patch["CI"] = "true"
            with mock.patch.dict(os.environ, env_patch, clear=True):
                with self.assertRaises(config.ConfigError):
                    config.get_active_semester_config(dotenv_path=dotenv_file)

                # CLI process must also exit non-zero
                proc = subprocess.run(
                    [sys.executable, os.path.join(ROOT_DIR, "config.py"), "--json"],
                    env=env_patch,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(proc.returncode, 0)

    def test_ci_true_fails_closed_on_empty_or_errored_db(self):
        fake_conn = FakeConn(lambda *a: [])
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://fake", "CI": "true"}, clear=False):
            with mock.patch.object(config.psycopg2, "connect", return_value=fake_conn):
                with self.assertRaises(config.ConfigError):
                    config.get_active_semester_config()

            with mock.patch.object(config.psycopg2, "connect", side_effect=RuntimeError("conn refused")):
                with self.assertRaises(config.ConfigError):
                    config.get_active_semester_config()

    def test_call_time_resolution_in_modules(self):
        for mod in (rebuild_db, main_mod, sheets_subject_extractor):
            self.assertFalse(hasattr(mod, "SPREADSHEET_ID"), f"{mod.__name__} still defines module-level SPREADSHEET_ID")

        with mock.patch.object(
            sheets_subject_extractor,
            "get_active_spreadsheet_id",
            return_value=("2027-spring", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"),
        ) as mock_cfg, mock.patch.object(sheets_subject_extractor, "get_sheets_service"), mock.patch.object(
            sheets_subject_extractor, "get_day_sheet_mapping", return_value={}
        ):
            with self.assertRaises(RuntimeError) as ctx:
                sheets_subject_extractor.extract_subjects_and_batches_from_api()
            self.assertIn("SHEET_STRUCTURE_INVALID", str(ctx.exception))
            mock_cfg.assert_called_once_with(override_id=None)


class TestUpgrade2And3SyncEngine(unittest.TestCase):
    def test_deterministic_slot_uid_and_multi_section_merge(self):
        weekly = {d: [] for d in sfs.DAYS_OF_WEEK}
        row1 = {
            "DAY": "Friday",
            "START_TIME": "02:30",
            "END_TIME": "05:15",
            "SUBJECT": "COAL Lab",
            "LOCATION": "Rawal 1",
            "SECTION": "CS-A",
            "BATCH": "BS 25 CS",
            "STATUS": None,
        }
        row2 = dict(row1, SECTION="AI-A")

        added1 = sfs._merge_slot_into_weekly_schedule(weekly, row1, "CL2001", "COAL Lab", "CS-A", "BS 25 CS", True, semester_id="2027-spring")
        added2 = sfs._merge_slot_into_weekly_schedule(weekly, row2, "CL2001", "COAL Lab", "AI-A", "BS 25 CS", True, semester_id="2027-spring")
        self.assertEqual(added1, 1)
        self.assertEqual(added2, 0)
        self.assertEqual(len(weekly["Friday"]), 1)

        slot = weekly["Friday"][0]
        self.assertEqual(slot["section"], "AI-A, CS-A")
        expected_uid = hashlib.sha256("2027-spring|Friday|02:30|COAL Lab|AI-A, CS-A|True".encode()).hexdigest()[:12]
        self.assertEqual(len(slot["slot_uid"]), 12)
        self.assertEqual(slot["slot_uid"], expected_uid)
        self.assertEqual(slot["id"], expected_uid)

        # Changing semester_id changes slot_uid deterministically
        other_uid = sfs.compute_slot_uid("2026-fall", "Friday", "02:30", "COAL Lab", "AI-A, CS-A", True)
        self.assertNotEqual(other_uid, expected_uid)

    def test_layer1_purity_removes_custom_activity_merging(self):
        self.assertFalse(hasattr(sfs, "_merge_custom_activities_from_existing"))

        queries = []

        def handler(op, sql, params, cur):
            if op == "execute":
                queries.append((sql, params))
                if "SELECT email FROM public.faculty_schedules" in sql:
                    return [{"email": "old.prof@nu.edu.pk"}, {"email": "keep.prof@nu.edu.pk"}]
                if "COALESCE(MAX(version), 0) + 1" in sql:
                    return [{"next_ver": 9}]
            return []

        fake_conn = FakeConn(handler)
        rec = {
            "email": "keep.prof@nu.edu.pk",
            "semester_id": "2027-spring",
            "name": "Prof Keep",
            "designation": "Lecturer",
            "department": "CS",
            "office": "C-101",
            "schedule": {
                "Monday": [
                    {"id": "abc123def456", "slot_uid": "abc123def456", "subject": "OOP", "start_time": "08:30", "end_time": "09:50"},
                    {"id": "act-99", "subject": "Private", "isCustom": True, "start_time": "10:00", "end_time": "11:00"},
                ],
                "Tuesday": [], "Wednesday": [], "Thursday": [], "Friday": [], "Saturday": [],
            },
            "courses": [],
            "total_credit_hours": 3.0,
        }

        with mock.patch.object(sfs.psycopg2, "connect", return_value=fake_conn), mock.patch.object(
            sfs, "execute_values", return_value=[{"is_insert": False}]
        ) as mock_ev:
            res = sfs.upsert_via_psycopg2([rec], "postgresql://fake", semester_id="2027-spring", prune_stale=True)

        self.assertFalse(res["aborted"])
        self.assertEqual(res["pruned"], 1)
        tuples = mock_ev.call_args[0][2]
        stored_sched = json.loads(tuples[0][6])
        self.assertEqual(len(stored_sched["Monday"]), 1)
        self.assertEqual(stored_sched["Monday"][0]["subject"], "OOP")
        self.assertEqual(tuples[0][11], 9)  # MAX(version)+1 floor
        self.assertTrue(any("DELETE FROM public.faculty_schedules" in sql for sql, _ in queries))

    def test_explicit_mode_required_and_no_silent_excel_fallback(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT_DIR, "sync_faculty_to_supabase.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--mode", proc.stderr)

        with mock.patch.object(sys, "argv", ["sync_faculty_to_supabase.py", "--mode", "sync"]), mock.patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://fake", "CI": "true"}, clear=False
        ), mock.patch.object(sfs, "sync_from_existing_database") as mock_sync, mock.patch.object(
            sfs, "read_course_allocations"
        ) as mock_read_excel:
            sfs.main()
            mock_sync.assert_called_once()
            mock_read_excel.assert_not_called()

    def test_zip_bomb_rejection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Non-zip file
            bad_file = os.path.join(tmpdir, "bad.xlsx")
            with open(bad_file, "wb") as f:
                f.write(b"NOT_A_ZIP")
            with self.assertRaises(sfs.JobError) as ctx:
                sfs.validate_xlsx_zip_safety(bad_file)
            self.assertEqual(ctx.exception.error_code, "INVALID_XLSX")

            # 2. > 500 entries
            many_file = os.path.join(tmpdir, "many.xlsx")
            with zipfile.ZipFile(many_file, "w") as zf:
                for i in range(501):
                    zf.writestr(f"xl/entry_{i}.xml", "x")
            with self.assertRaises(sfs.JobError) as ctx:
                sfs.validate_xlsx_zip_safety(many_file)
            self.assertEqual(ctx.exception.error_code, "ZIP_BOMB_DETECTED")

            # 3. > 50 MB uncompressed (compression ratio bomb)
            huge_file = os.path.join(tmpdir, "huge.xlsx")
            with zipfile.ZipFile(huge_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("xl/huge.xml", b"0" * (51 * 1024 * 1024))
            with self.assertRaises(sfs.JobError) as ctx:
                sfs.validate_xlsx_zip_safety(huge_file)
            self.assertEqual(ctx.exception.error_code, "ZIP_BOMB_DETECTED")

            # 4. Path traversal
            trav_file = os.path.join(tmpdir, "trav.xlsx")
            with zipfile.ZipFile(trav_file, "w") as zf:
                zf.writestr("../../etc/passwd", "x")
            with self.assertRaises(sfs.JobError) as ctx:
                sfs.validate_xlsx_zip_safety(trav_file)
            self.assertEqual(ctx.exception.error_code, "INVALID_XLSX")

            # 5. Real workbook passes cleanly
            sfs.validate_xlsx_zip_safety(sfs.DEFAULT_EXCEL_PATH)

    def test_11_key_parsed_allocations_schema(self):
        allocs = sfs.read_course_allocations(sfs.DEFAULT_EXCEL_PATH, year=2026, season="fall")
        serialized = sfs.serialize_parsed_allocations(allocs[:10])
        expected_keys = {
            "sheet", "is_lab", "course_code", "course_title", "credit_hours",
            "coordinator", "raw_section", "raw_instructor", "batch",
            "timetable_section", "canonical_subject",
        }
        for item in serialized:
            self.assertEqual(set(item.keys()), expected_keys)

    def test_draft_job_atomic_claim_zero_rows_exits_cleanly(self):
        fake_conn = FakeConn(lambda *a: [])
        with mock.patch.object(sfs.psycopg2, "connect", return_value=fake_conn), mock.patch.object(
            sfs, "download_storage_object"
        ) as mock_dl:
            res = sfs.run_draft_job(
                "11111111-1111-1111-1111-111111111111",
                "postgresql://fake",
                "https://supa.example",
                "svc-key",
            )
        self.assertEqual(res, {"claimed": False, "job_id": "11111111-1111-1111-1111-111111111111"})
        mock_dl.assert_not_called()

    def test_draft_job_success_promotes_snapshot_and_deletes_uploads(self):
        job_id = "22222222-2222-2222-2222-222222222222"
        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"
        executed = []

        def db_handler(op, sql, params, cur):
            if op == "execute":
                executed.append((sql, params))
                if "UPDATE public.ingestion_jobs SET status = 'RUNNING'" in sql:
                    return [{
                        "id": job_id,
                        "semester_id": "2027-spring",
                        "google_sheet_id": sheet_id,
                        "allocation_storage_path": f"uploads/2027-spring/{job_id}.xlsx",
                        "requested_by": "admin@nu.edu.pk",
                        "status": "RUNNING",
                    }]
                if "SELECT id, academic_year, season FROM public.semesters" in sql:
                    return [{"id": "2027-spring", "academic_year": 2027, "season": "Spring"}]
                if "SELECT * FROM public.ingestion_jobs WHERE id = %s FOR UPDATE" in sql:
                    return [{"id": job_id, "status": "RUNNING"}]
                if "FROM public.semester_snapshots WHERE semester_id = %s AND status = 'DRAFT' FOR UPDATE" in sql:
                    return [{"id": "old-draft-id", "allocation_storage_path": "snapshots/2027-spring/old.xlsx"}]
                if "COALESCE(MAX(revision_number), 0) + 1" in sql:
                    return [{"next_rev": 4}]
            return []

        def fake_dl(url, key, src, dst):
            with zipfile.ZipFile(dst, "w") as zf:
                zf.writestr("[Content_Types].xml", "<Types/>")

        fake_allocs = [{
            "sheet": "Computing-Theory", "is_lab": False, "course_code": "CS1001",
            "course_title": "OOP", "credit_hours": 3.0, "coordinator": "X",
            "raw_section": "BCS-2A", "raw_instructor": "Dr. Test",
            "batch": "BS 26 CS", "timetable_section": "CS-A", "canonical_subject": "OOP",
        }]
        fake_records = [{
            "email": "test@nu.edu.pk", "semester_id": "2027-spring", "name": "Dr. Test",
            "designation": "AP", "department": "CS", "office": "C-101",
            "schedule": {d: [] for d in sfs.DAYS_OF_WEEK},
            "courses": [], "total_weekly_slots": 2, "total_credit_hours": 3.0,
            "schedule_hash": "hash123",
        }]
        fake_audit = {"metrics": {"total_allocations": 1}}

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(db_handler)))
            stack.enter_context(mock.patch.object(sfs, "execute_values"))
            stack.enter_context(mock.patch.object(sfs, "download_storage_object", side_effect=fake_dl))
            mock_read = stack.enter_context(mock.patch.object(sfs, "read_course_allocations", return_value=fake_allocs))
            mock_build = stack.enter_context(mock.patch("rebuild_db.build_sqlite_from_google_sheet"))
            stack.enter_context(mock.patch.object(sfs, "decode_faculty_bin", return_value=[]))
            stack.enter_context(mock.patch.object(sfs, "compile_faculty_schedules", return_value=(fake_records, fake_audit, "csv")))
            mock_copy = stack.enter_context(mock.patch.object(sfs, "copy_storage_object"))
            mock_del = stack.enter_context(mock.patch.object(sfs, "delete_storage_object"))

            res = sfs.run_draft_job(job_id, "postgresql://fake", "https://supa.example", "svc-key")

        self.assertTrue(res["claimed"])
        self.assertEqual(res["revision_number"], 4)
        # Season lowercased to 'spring' when calling read_course_allocations
        mock_read.assert_called_once()
        self.assertEqual(mock_read.call_args.kwargs["year"], 2027)
        self.assertEqual(mock_read.call_args.kwargs["season"], "spring")
        # Isolated /tmp DB paths used
        self.assertTrue(mock_build.call_args.kwargs["course_db"].startswith("/tmp/"))
        self.assertTrue(mock_build.call_args.kwargs["lab_db"].startswith("/tmp/"))
        # Copied to snapshots/<sem>/<snap>.xlsx and deleted uploads/... + old draft object
        snap_id = res["snapshot_id"]
        mock_copy.assert_called_once_with(
            "https://supa.example", "svc-key",
            f"uploads/2027-spring/{job_id}.xlsx",
            f"snapshots/2027-spring/{snap_id}.xlsx",
        )
        deleted_paths = [c.args[2] for c in mock_del.call_args_list]
        self.assertIn(f"uploads/2027-spring/{job_id}.xlsx", deleted_paths)
        self.assertIn("snapshots/2027-spring/old.xlsx", deleted_paths)
        # Never touches faculty_schedules
        self.assertFalse(any("faculty_schedules" in sql for sql, _ in executed))

    def test_draft_job_failure_preserves_uploads_and_marks_failed(self):
        job_id = "33333333-3333-3333-3333-333333333333"
        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"
        failed_updates = []

        def db_handler(op, sql, params, cur):
            if op == "execute":
                if "UPDATE public.ingestion_jobs SET status = 'RUNNING'" in sql:
                    return [{
                        "id": job_id,
                        "semester_id": "2027-spring",
                        "google_sheet_id": sheet_id,
                        "allocation_storage_path": f"uploads/2027-spring/{job_id}.xlsx",
                        "requested_by": "admin@nu.edu.pk",
                        "status": "RUNNING",
                    }]
                if "SELECT id, academic_year, season FROM public.semesters" in sql:
                    return [{"id": "2027-spring", "academic_year": 2027, "season": "Spring"}]
                if "SET status = 'FAILED'" in sql:
                    failed_updates.append(params)
            return []

        def fake_dl(url, key, src, dst):
            with zipfile.ZipFile(dst, "w") as zf:
                zf.writestr("[Content_Types].xml", "<Types/>")

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(db_handler)))
            stack.enter_context(mock.patch.object(sfs, "download_storage_object", side_effect=fake_dl))
            stack.enter_context(mock.patch.object(sfs, "read_course_allocations", return_value=[{"sheet": "S"}]))
            stack.enter_context(
                mock.patch("rebuild_db.build_sqlite_from_google_sheet", side_effect=RuntimeError("SHEET_ACCESS_DENIED: 403"))
            )
            mock_del = stack.enter_context(mock.patch.object(sfs, "delete_storage_object"))

            with self.assertRaises(RuntimeError):
                sfs.run_draft_job(job_id, "postgresql://fake", "https://supa.example", "svc-key")

        # uploads/... preserved on failure for retry_ingest_job
        mock_del.assert_not_called()
        self.assertEqual(len(failed_updates), 1)
        self.assertEqual(failed_updates[0][0], "SHEET_ACCESS_DENIED")

    def test_draft_job_zombie_check_deletes_copied_snapshot(self):
        job_id = "44444444-4444-4444-4444-444444444444"
        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"

        def db_handler(op, sql, params, cur):
            if op == "execute":
                if "UPDATE public.ingestion_jobs SET status = 'RUNNING'" in sql:
                    return [{
                        "id": job_id,
                        "semester_id": "2027-spring",
                        "google_sheet_id": sheet_id,
                        "allocation_storage_path": f"uploads/2027-spring/{job_id}.xlsx",
                        "requested_by": "admin@nu.edu.pk",
                        "status": "RUNNING",
                    }]
                if "SELECT id, academic_year, season FROM public.semesters" in sql:
                    return [{"id": "2027-spring", "academic_year": 2027, "season": "Spring"}]
                if "SELECT * FROM public.ingestion_jobs WHERE id = %s FOR UPDATE" in sql:
                    return [{"id": job_id, "status": "CANCELLED"}]
            return []

        def fake_dl(url, key, src, dst):
            with zipfile.ZipFile(dst, "w") as zf:
                zf.writestr("[Content_Types].xml", "<Types/>")

        fake_records = [{
            "email": "test@nu.edu.pk", "semester_id": "2027-spring", "name": "Dr. Test",
            "designation": "AP", "department": "CS", "office": "C-101",
            "schedule": {d: [] for d in sfs.DAYS_OF_WEEK},
            "courses": [], "total_weekly_slots": 1, "total_credit_hours": 3.0, "schedule_hash": "h",
        }]

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(db_handler)))
            stack.enter_context(mock.patch.object(sfs, "download_storage_object", side_effect=fake_dl))
            stack.enter_context(mock.patch.object(sfs, "read_course_allocations", return_value=[{"sheet": "S"}]))
            stack.enter_context(mock.patch("rebuild_db.build_sqlite_from_google_sheet"))
            stack.enter_context(mock.patch.object(sfs, "decode_faculty_bin", return_value=[]))
            stack.enter_context(mock.patch.object(sfs, "compile_faculty_schedules", return_value=(fake_records, {"metrics": {}}, "csv")))
            stack.enter_context(mock.patch.object(sfs, "copy_storage_object"))
            mock_del = stack.enter_context(mock.patch.object(sfs, "delete_storage_object"))

            with self.assertRaises(sfs.JobError) as ctx:
                sfs.run_draft_job(job_id, "postgresql://fake", "https://supa.example", "svc-key")

        self.assertEqual(ctx.exception.error_code, "JOB_CANCELLED_OR_TIMED_OUT")
        deleted_paths = [c.args[2] for c in mock_del.call_args_list]
        self.assertTrue(any(p.startswith("snapshots/2027-spring/") for p in deleted_paths))
        self.assertNotIn(f"uploads/2027-spring/{job_id}.xlsx", deleted_paths)

    def test_draft_job_base_exception_marks_failed(self):
        job_id = "55555555-5555-5555-5555-555555555555"
        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"
        failed_updates = []

        def db_handler(op, sql, params, cur):
            if op == "execute":
                if "UPDATE public.ingestion_jobs SET status = 'RUNNING'" in sql:
                    return [{
                        "id": job_id,
                        "semester_id": "2027-spring",
                        "google_sheet_id": sheet_id,
                        "allocation_storage_path": f"uploads/2027-spring/{job_id}.xlsx",
                        "requested_by": "admin@nu.edu.pk",
                        "status": "RUNNING",
                    }]
                if "SELECT id, academic_year, season FROM public.semesters" in sql:
                    return [{"id": "2027-spring", "academic_year": 2027, "season": "Spring"}]
                if "SET status = 'FAILED'" in sql:
                    failed_updates.append(params)
            return []

        with mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(db_handler)), mock.patch.object(
            sfs, "download_storage_object", side_effect=SystemExit(1)
        ):
            with self.assertRaises(SystemExit):
                sfs.run_draft_job(job_id, "postgresql://fake", "https://supa.example", "svc-key")

        self.assertEqual(len(failed_updates), 1)
        self.assertEqual(failed_updates[0][0], "INTERNAL_ERROR")

    def test_refresh_draft_failure_preserves_old_draft_and_success_swaps_1_to_1(self):
        job_id = "66666666-6666-6666-6666-666666666666"
        src_snap_id = "77777777-7777-7777-7777-777777777777"
        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"
        parsed_allocs = [{
            "sheet": "Computing-Theory", "is_lab": False, "course_code": "CS1001",
            "course_title": "OOP", "credit_hours": 3.0, "coordinator": "X",
            "raw_section": "BCS-2A", "raw_instructor": "Dr. Test",
            "batch": "BS 26 CS", "timetable_section": "CS-A", "canonical_subject": "OOP",
        }]

        # Case A: Failure leaves old DRAFT untouched
        failed_updates = []

        def fail_db(op, sql, params, cur):
            if op == "execute":
                if "UPDATE public.ingestion_jobs SET status = 'RUNNING'" in sql:
                    return [{
                        "id": job_id,
                        "semester_id": "2027-spring",
                        "google_sheet_id": sheet_id,
                        "source_snapshot_id": src_snap_id,
                        "requested_by": "admin@nu.edu.pk",
                        "status": "RUNNING",
                    }]
                if "FROM public.semester_snapshots ss JOIN public.semesters" in sql:
                    return [{
                        "id": src_snap_id, "status": "DRAFT",
                        "parsed_allocations": parsed_allocs,
                        "allocation_storage_path": f"snapshots/2027-spring/{src_snap_id}.xlsx",
                        "academic_year": 2027, "season": "Spring",
                    }]
                if "SET status = 'FAILED'" in sql:
                    failed_updates.append(params)
            return []

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(fail_db)))
            stack.enter_context(
                mock.patch("rebuild_db.build_sqlite_from_google_sheet", side_effect=RuntimeError("OAUTH_TOKEN_EXPIRED"))
            )
            mock_del = stack.enter_context(mock.patch.object(sfs, "delete_storage_object"))
            with self.assertRaises(RuntimeError):
                sfs.run_refresh_draft_job(job_id, "postgresql://fake", "https://supa.example", "svc-key")

        mock_del.assert_not_called()
        self.assertEqual(failed_updates[0][0], "OAUTH_TOKEN_EXPIRED")

        # Case B: Success creates 1:1 object and deletes old snapshot object after commit
        def ok_db(op, sql, params, cur):
            if op == "execute":
                if "UPDATE public.ingestion_jobs SET status = 'RUNNING'" in sql:
                    return [{
                        "id": job_id,
                        "semester_id": "2027-spring",
                        "google_sheet_id": sheet_id,
                        "source_snapshot_id": src_snap_id,
                        "requested_by": "admin@nu.edu.pk",
                        "status": "RUNNING",
                    }]
                if "FROM public.semester_snapshots ss JOIN public.semesters" in sql:
                    return [{
                        "id": src_snap_id, "status": "DRAFT",
                        "parsed_allocations": parsed_allocs,
                        "allocation_storage_path": f"snapshots/2027-spring/{src_snap_id}.xlsx",
                        "academic_year": 2027, "season": "Spring",
                    }]
                if "SELECT * FROM public.ingestion_jobs WHERE id = %s FOR UPDATE" in sql:
                    return [{"id": job_id, "status": "RUNNING"}]
                if "SELECT status FROM public.semester_snapshots WHERE id = %s" in sql:
                    return [{"status": "DRAFT"}]
                if "FROM public.semester_snapshots WHERE semester_id = %s AND status = 'DRAFT' FOR UPDATE" in sql:
                    return [{"id": src_snap_id, "allocation_storage_path": f"snapshots/2027-spring/{src_snap_id}.xlsx"}]
                if "COALESCE(MAX(revision_number), 0) + 1" in sql:
                    return [{"next_rev": 5}]
            return []

        fake_records = [{
            "email": "test@nu.edu.pk", "semester_id": "2027-spring", "name": "Dr. Test",
            "designation": "AP", "department": "CS", "office": "C-101",
            "schedule": {d: [] for d in sfs.DAYS_OF_WEEK},
            "courses": [], "total_weekly_slots": 1, "total_credit_hours": 3.0, "schedule_hash": "h2",
        }]
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(ok_db)))
            stack.enter_context(mock.patch.object(sfs, "execute_values"))
            stack.enter_context(mock.patch("rebuild_db.build_sqlite_from_google_sheet"))
            stack.enter_context(mock.patch.object(sfs, "decode_faculty_bin", return_value=[]))
            stack.enter_context(mock.patch.object(sfs, "compile_faculty_schedules", return_value=(fake_records, {"metrics": {}}, "csv")))
            mock_copy = stack.enter_context(mock.patch.object(sfs, "copy_storage_object"))
            mock_del = stack.enter_context(mock.patch.object(sfs, "delete_storage_object"))

            res = sfs.run_refresh_draft_job(job_id, "postgresql://fake", "https://supa.example", "svc-key")

        new_snap_id = res["snapshot_id"]
        mock_copy.assert_called_once_with(
            "https://supa.example", "svc-key",
            f"snapshots/2027-spring/{src_snap_id}.xlsx",
            f"snapshots/2027-spring/{new_snap_id}.xlsx",
        )
        mock_del.assert_called_once_with(
            "https://supa.example", "svc-key",
            f"snapshots/2027-spring/{src_snap_id}.xlsx",
        )

    def test_reconcile_snapshot_success_toctou_and_failure_callback(self):
        snap_id = "88888888-8888-8888-8888-888888888888"
        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"
        parsed_allocs = [{
            "sheet": "Computing-Theory", "is_lab": False, "course_code": "CS1001",
            "course_title": "OOP", "credit_hours": 3.0, "coordinator": "X",
            "raw_section": "BCS-2A", "raw_instructor": "Dr. Test",
            "batch": "BS 26 CS", "timetable_section": "CS-A", "canonical_subject": "OOP",
        }]
        fake_records = [{
            "email": "test@nu.edu.pk", "semester_id": "2027-spring", "name": "Dr. Test",
            "designation": "AP", "department": "CS", "office": "C-101",
            "schedule": {d: [] for d in sfs.DAYS_OF_WEEK},
            "courses": [], "total_weekly_slots": 1, "total_credit_hours": 3.0, "schedule_hash": "h",
        }]

        # 1. Success path sends SYNCED callback, uses prune_stale=True, checks state_version
        def ok_db(op, sql, params, cur):
            if op == "execute" and "FROM public.semester_snapshots ss" in sql:
                return [{
                    "id": snap_id, "semester_id": "2027-spring", "status": "LIVE",
                    "snap_sheet_id": sheet_id, "sem_sheet_id": sheet_id,
                    "parsed_allocations": parsed_allocs, "allocation_storage_path": None,
                    "academic_year": 2027, "season": "Spring",
                    "state_version": 5, "is_published": True, "deleted_at": None,
                }]
            return []

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(ok_db)))
            stack.enter_context(mock.patch("rebuild_db.build_sqlite_from_google_sheet"))
            stack.enter_context(mock.patch.object(sfs, "decode_faculty_bin", return_value=[]))
            stack.enter_context(mock.patch.object(sfs, "compile_faculty_schedules", return_value=(fake_records, {"metrics": {}}, "csv")))
            mock_upsert = stack.enter_context(mock.patch.object(sfs, "upsert_via_psycopg2", return_value={"aborted": False, "inserted": 1, "updated": 0, "pruned": 0}))
            mock_cb = stack.enter_context(mock.patch.object(sfs, "send_sync_callback"))

            res = sfs.run_reconcile_snapshot(snap_id, 5, "postgresql://fake", portal_callback_url="https://cb.example", callback_secret="sec")

        self.assertFalse(res["aborted"])
        self.assertTrue(mock_upsert.call_args.kwargs["prune_stale"])
        self.assertEqual(mock_upsert.call_args.kwargs["expected_state_version"], 5)
        self.assertFalse(mock_upsert.call_args.kwargs["require_auto_enabled"])
        mock_cb.assert_called_once_with(
            action="faculty_sync_callback",
            semester_id="2027-spring",
            state_version=5,
            status="SYNCED",
            error_message=None,
            portal_callback_url="https://cb.example",
            callback_secret="sec",
        )

        # 2. Failure path sends FAILED callback
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(ok_db)))
            stack.enter_context(mock.patch("rebuild_db.build_sqlite_from_google_sheet", side_effect=RuntimeError("SHEET_ACCESS_DENIED: 403")))
            mock_cb = stack.enter_context(mock.patch.object(sfs, "send_sync_callback"))

            with self.assertRaises(RuntimeError):
                sfs.run_reconcile_snapshot(snap_id, 5, "postgresql://fake", portal_callback_url="https://cb.example", callback_secret="sec")

        self.assertEqual(mock_cb.call_args.kwargs["status"], "FAILED")
        self.assertIn("SHEET_ACCESS_DENIED", mock_cb.call_args.kwargs["error_message"])

        # 3. TOCTOU mismatch aborts cleanly without touching DB or sending callback
        def stale_db(op, sql, params, cur):
            if op == "execute" and "FROM public.semester_snapshots ss" in sql:
                return [{
                    "id": snap_id, "semester_id": "2027-spring", "status": "LIVE",
                    "snap_sheet_id": sheet_id, "sem_sheet_id": sheet_id,
                    "parsed_allocations": parsed_allocs, "allocation_storage_path": None,
                    "academic_year": 2027, "season": "Spring",
                    "state_version": 6, "is_published": True, "deleted_at": None,
                }]
            return []

        with mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(stale_db)), mock.patch.object(
            sfs, "send_sync_callback"
        ) as mock_cb:
            stale_res = sfs.run_reconcile_snapshot(snap_id, 5, "postgresql://fake")
        self.assertTrue(stale_res["aborted"])
        mock_cb.assert_not_called()

    def test_continuous_sync_guards_and_year_season_propagation(self):
        # 1. Verify translate_section_code uses Spring 2027 algebra when semester is Spring 2027
        row_spring = {
            "email": "spring.prof@nu.edu.pk",
            "semester_id": "2027-spring",
            "name": "Prof Spring",
            "designation": "AP",
            "department": "CS",
            "office": "C-101",
            "schedule": {},
            "courses": [{"course_code": "CS1002", "course_name": "OOP", "canonical_subject": "OOP", "sections": ["BCS-2A"], "is_lab": False}],
            "total_credit_hours": 3.0,
        }
        conn_t = sqlite3.connect(":memory:")
        conn_t.row_factory = sqlite3.Row
        conn_t.execute("CREATE TABLE timetable (ID INTEGER PRIMARY KEY, DAY TEXT, START_TIME TEXT, END_TIME TEXT, SUBJECT TEXT, CLASSROOM TEXT, SECTION TEXT, BATCH TEXT, STATUS TEXT)")
        conn_t.execute("INSERT INTO timetable VALUES (1, 'Monday', '08:30', '09:50', 'OOP', 'C-301', 'CS-A', 'BS 26 CS', NULL)")
        conn_l = sqlite3.connect(":memory:")
        conn_l.row_factory = sqlite3.Row
        conn_l.execute("CREATE TABLE timetable (ID INTEGER PRIMARY KEY, DAY TEXT, START_TIME TEXT, END_TIME TEXT, SUBJECT TEXT, LAB TEXT, SECTION TEXT, BATCH TEXT, STATUS TEXT)")
        try:
            reconciled = sfs.reconcile_existing_db_rows(
                [row_spring], conn_t.cursor(), conn_l.cursor(), semester_id="2027-spring", year=2027, season="Spring"
            )
        finally:
            conn_t.close()
            conn_l.close()

        self.assertEqual(reconciled[0]["courses"][0]["allocations"], [{"batch": "BS 26 CS", "section": "CS-A"}])
        self.assertEqual(len(reconciled[0]["schedule"]["Monday"]), 1)

        # 2. Verify upsert_via_psycopg2 FOR UPDATE guard aborts on PAUSED_POST_ROLLBACK / TOCTOU / inactive
        for sem_state, expected_reason in [
            ({"status": "COMMITTED", "is_active": False, "is_published": True, "sync_policy": "AUTO_ENABLED", "state_version": 3, "deleted_at": None}, "SEMESTER_INACTIVE"),
            ({"status": "COMMITTED", "is_active": True, "is_published": False, "sync_policy": "AUTO_ENABLED", "state_version": 3, "deleted_at": None}, "SEMESTER_UNPUBLISHED"),
            ({"status": "COMMITTED", "is_active": True, "is_published": True, "sync_policy": "PAUSED_POST_ROLLBACK", "state_version": 3, "deleted_at": None}, "SYNC_POLICY_PAUSED_POST_ROLLBACK"),
            ({"status": "COMMITTED", "is_active": True, "is_published": True, "sync_policy": "AUTO_ENABLED", "state_version": 4, "deleted_at": None}, "TOCTOU_STATE_VERSION_MISMATCH"),
            ({"status": "SOFT_DELETED", "is_active": False, "is_published": False, "sync_policy": "AUTO_ENABLED", "state_version": 3, "deleted_at": "2026-01-01"}, "SEMESTER_MISSING_OR_DELETED"),
        ]:
            def guard_handler(op, sql, params, cur, st=sem_state):
                if op == "execute" and "FOR UPDATE" in sql:
                    return [st]
                return []

            fake_conn = FakeConn(guard_handler)
            with mock.patch.object(sfs.psycopg2, "connect", return_value=fake_conn):
                out = sfs.upsert_via_psycopg2(
                    reconciled,
                    "postgresql://fake",
                    semester_id="2027-spring",
                    expected_state_version=3,
                    require_active=True,
                    require_published=True,
                    require_auto_enabled=True,
                )
            self.assertTrue(out["aborted"])
            self.assertEqual(out["reason"], expected_reason)
            self.assertTrue(fake_conn.rolled_back)
            self.assertFalse(fake_conn.committed)


class TestUpgrade4And5HardeningAndContracts(unittest.TestCase):
    def test_oauth_refresh_error_fails_closed_in_ci(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tok = Path(tmpdir) / "token.json"
            cred = Path(tmpdir) / "credentials.json"
            tok.write_text('{"token":"x","refresh_token":"r","client_id":"c","client_secret":"s"}', encoding="utf-8")
            cred.write_text('{"installed":{"client_id":"c"}}', encoding="utf-8")

            fake_creds = mock.MagicMock()
            fake_creds.valid = False
            fake_creds.expired = True
            fake_creds.refresh_token = "r"
            fake_creds.refresh.side_effect = RefreshError("invalid_grant")

            with mock.patch.dict(os.environ, {"CI": "true"}, clear=False), mock.patch.object(
                databaseHandler.Credentials, "from_authorized_user_file", return_value=fake_creds
            ), mock.patch.object(databaseHandler.InstalledAppFlow, "from_client_secrets_file") as mock_flow:
                with self.assertRaises(RuntimeError) as ctx:
                    databaseHandler.get_sheets_service(token_path=tok, credentials_path=cred)
            self.assertIn("OAUTH_TOKEN_EXPIRED", str(ctx.exception))
            mock_flow.assert_not_called()

    def test_empty_grid_data_raises_sheet_structure_invalid(self):
        fake_service = mock.MagicMock()
        fake_service.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "Monday"}, "data": []}]
        }
        with self.assertRaises(RuntimeError) as ctx:
            databaseHandler.get_raw_sheet(fake_service, "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD", "Monday")
        self.assertIn("SHEET_STRUCTURE_INVALID", str(ctx.exception))

    def test_google_http_retry_and_access_denied(self):
        sleeps = []
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise make_http_error(429, "Rate limit")
            if calls["n"] == 2:
                raise make_http_error(503, "Backend unavailable")
            return {"ok": True}

        res = databaseHandler.execute_google_api_call(flaky, sleep_fn=sleeps.append)
        self.assertEqual(res, {"ok": True})
        self.assertEqual(sleeps, [2, 6])

        # Exhausts after 3 attempts on persistent 500
        sleeps2 = []
        with self.assertRaises(HttpError):
            databaseHandler.execute_google_api_call(
                mock.MagicMock(side_effect=make_http_error(500, "Server error")),
                sleep_fn=sleeps2.append,
            )
        self.assertEqual(sleeps2, [2, 6])

        # Fails immediately without retry on 403
        sleeps3 = []
        with self.assertRaises(RuntimeError) as ctx:
            databaseHandler.execute_google_api_call(
                mock.MagicMock(side_effect=make_http_error(403, "Forbidden")),
                sleep_fn=sleeps3.append,
            )
        self.assertIn("SHEET_ACCESS_DENIED", str(ctx.exception))
        self.assertEqual(sleeps3, [])

    def test_rebuild_db_fails_loudly_and_does_not_call_static_gen(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            t_db = os.path.join(tmpdir, "t.db")
            l_db = os.path.join(tmpdir, "l.db")
            with mock.patch.object(
                rebuild_db, "get_active_spreadsheet_id", return_value=("2027-spring", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD")
            ), mock.patch.object(rebuild_db, "get_sheets_service"), mock.patch.object(
                rebuild_db, "get_day_sheet_mapping", return_value={"Monday": "Monday"}
            ), mock.patch.object(
                rebuild_db, "read_and_clean_classroom_df", side_effect=ValueError("SHEET_STRUCTURE_INVALID: broken Monday")
            ):
                with self.assertRaises(ValueError):
                    rebuild_db.rebuild(course_db=t_db, lab_db=l_db)

    def test_generate_static_json_wipes_stale_bins(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subj_db = os.path.join(tmpdir, "subjects.db")
            course_db = os.path.join(tmpdir, "course.db")
            lab_db = os.path.join(tmpdir, "lab.db")
            out_dir = os.path.join(tmpdir, "out")
            sched_dir = os.path.join(out_dir, "schedules")
            os.makedirs(sched_dir, exist_ok=True)
            stale_bin = os.path.join(sched_dir, "STALE_BATCH__OLD-A.bin")
            with open(stale_bin, "w", encoding="utf-8") as f:
                f.write("stale")

            c_s = sqlite3.connect(subj_db)
            try:
                c_s.execute("CREATE TABLE batches (id INTEGER PRIMARY KEY, name TEXT, color_hex TEXT)")
                c_s.execute("CREATE TABLE subjects (id INTEGER PRIMARY KEY, name TEXT, short_name TEXT)")
                c_s.execute("CREATE TABLE batch_subjects (id INTEGER PRIMARY KEY, batch_id INTEGER, subject_id INTEGER)")
                c_s.execute("INSERT INTO batches VALUES (1, 'BS 26 CS', '#000000')")
                c_s.execute("INSERT INTO subjects VALUES (1, 'OOP', 'OOP')")
                c_s.execute("INSERT INTO batch_subjects VALUES (1, 1, 1)")
                c_s.commit()
            finally:
                c_s.close()

            c_c = sqlite3.connect(course_db)
            try:
                c_c.execute("CREATE TABLE timetable (ID INTEGER PRIMARY KEY, DAY TEXT, START_TIME TEXT, END_TIME TEXT, SUBJECT TEXT, CLASSROOM TEXT, SECTION TEXT, BATCH TEXT, STATUS TEXT)")
                c_c.execute("INSERT INTO timetable VALUES (1, 'Monday', '08:30', '09:50', 'OOP', 'C-301', 'CS-A', 'BS 26 CS', NULL)")
                c_c.commit()
            finally:
                c_c.close()

            c_l = sqlite3.connect(lab_db)
            try:
                c_l.execute("CREATE TABLE timetable (ID INTEGER PRIMARY KEY, DAY TEXT, START_TIME TEXT, END_TIME TEXT, SUBJECT TEXT, LAB TEXT, SECTION TEXT, BATCH TEXT, STATUS TEXT)")
                c_l.commit()
            finally:
                c_l.close()

            with mock.patch.object(generate_static_json, "SUBJECTS_DB", subj_db), mock.patch.object(
                generate_static_json, "COURSE_DB", course_db
            ), mock.patch.object(generate_static_json, "LAB_DB", lab_db), mock.patch.object(
                generate_static_json, "OUTPUT_DIR", out_dir
            ):
                generate_static_json.generate_static_data()

            self.assertFalse(os.path.exists(stale_bin))
            self.assertTrue(os.path.exists(os.path.join(sched_dir, "BS_26_CS__CS-A.bin")))

    def test_hmac_callback_signing_contract(self):
        raw_body = sfs.build_sync_callback_body("2027-spring", 12, "SYNCED", None)
        self.assertEqual(
            raw_body,
            '{"semester_id":"2027-spring","state_version":12,"status":"SYNCED","error_message":null}',
        )
        headers = sfs.sign_sync_callback(raw_body, "super-secret", timestamp=1700000000)
        expected_sig = hmac.new(b"super-secret", f"1700000000.{raw_body}".encode("utf-8"), hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-Timestamp"], "1700000000")
        self.assertEqual(headers["X-Signature"], f"sha256={expected_sig}")
        self.assertEqual(headers["Content-Type"], "application/json")

        fake_resp = mock.MagicMock()
        fake_resp.ok = True
        fake_resp.json.return_value = {"ok": True, "updated": True}
        with mock.patch.object(sfs.requests, "post", return_value=fake_resp) as mock_post:
            res = sfs.send_sync_callback(
                "student_sync_callback",
                "2027-spring",
                12,
                "SYNCED",
                portal_callback_url="https://fast-faculty-timetable.pages.dev/",
                callback_secret="super-secret",
            )
        self.assertTrue(res["updated"])
        self.assertEqual(
            mock_post.call_args.args[0],
            "https://fast-faculty-timetable.pages.dev/api/semesters?action=student_sync_callback",
        )

    def test_sync_yml_routes_and_concurrency_groups(self):
        yml_path = os.path.join(ROOT_DIR, ".github", "workflows", "sync.yml")
        with open(yml_path, "r", encoding="utf-8") as f:
            content = f.read()

        for expected in (
            "sheet_updated",
            "ingest_draft_job",
            "refresh_draft_sheet",
            "reconcile_faculty_from_db",
            "publish_student_semester",
            "group: ingest-${{ github.event.client_payload.job_id }}",
            "group: reconcile-${{ github.event.client_payload.snapshot_id }}",
            "group: student-portal-deploy",
            "cancel-in-progress: false",
            "git add -A frontend/data/ *.db",
            "git pull --rebase",
            "--mode draft --job-id",
            "--mode refresh-draft --job-id",
            "--mode reconcile-snapshot",
            "--mode sync --semester-id auto",
            "student_sync_callback",
            "DATABASE_URL: ${{ secrets.DATABASE_URL }}",
        ):
            self.assertIn(expected, content)

    def test_standalone_apps_script_fail_closed_and_dual_hash(self):
        js_path = os.path.join(ROOT_DIR, "standalone_apps_script.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js = f.read()

        self.assertNotIn("1vlTuotLw34fedME3gNQj09cZw-todVomxAiu5P1wZ6Q", js)
        for expected in (
            "/api/semesters?action=sync_target",
            "SYNC_WATCHER_SECRET",
            "Cache-Control",
            "no-cache",
            'target.sync_policy !== "AUTO_ENABLED"',
            "getValues()",
            "getBackgrounds()",
            "LAST_SHEET_KEY",
            'semesterId + ":" + SHEET_ID + ":" + currentHash',
        ):
            self.assertIn(expected, js)

    def test_reconcile_snapshot_fallback_storage_and_snapshot_rows(self):
        snap_id = "99999999-9999-9999-9999-999999999999"
        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"

        # Fallback 1: allocation_storage_path when parsed_allocations is None
        def db_storage_fallback(op, sql, params, cur):
            if op == "execute" and "FROM public.semester_snapshots ss" in sql:
                return [{
                    "id": snap_id, "semester_id": "2027-spring", "status": "LIVE",
                    "snap_sheet_id": sheet_id, "sem_sheet_id": sheet_id,
                    "parsed_allocations": None,
                    "allocation_storage_path": f"snapshots/2027-spring/{snap_id}.xlsx",
                    "academic_year": 2027, "season": "Spring",
                    "state_version": 2, "is_published": True, "deleted_at": None,
                }]
            return []

        def fake_dl(url, key, src, dst):
            with zipfile.ZipFile(dst, "w") as zf:
                zf.writestr("[Content_Types].xml", "<Types/>")

        fake_records = [{
            "email": "test@nu.edu.pk", "semester_id": "2027-spring", "name": "Dr. Test",
            "designation": "AP", "department": "CS", "office": "C-101",
            "schedule": {d: [] for d in sfs.DAYS_OF_WEEK},
            "courses": [], "total_weekly_slots": 1, "total_credit_hours": 3.0, "schedule_hash": "h",
        }]

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(db_storage_fallback)))
            stack.enter_context(mock.patch("rebuild_db.build_sqlite_from_google_sheet"))
            mock_dl = stack.enter_context(mock.patch.object(sfs, "download_storage_object", side_effect=fake_dl))
            mock_read = stack.enter_context(mock.patch.object(sfs, "read_course_allocations", return_value=[{"sheet": "S"}]))
            stack.enter_context(mock.patch.object(sfs, "decode_faculty_bin", return_value=[]))
            stack.enter_context(mock.patch.object(sfs, "compile_faculty_schedules", return_value=(fake_records, {"metrics": {}}, "csv")))
            stack.enter_context(mock.patch.object(sfs, "upsert_via_psycopg2", return_value={"aborted": False}))
            stack.enter_context(mock.patch.object(sfs, "send_sync_callback"))
            sfs.run_reconcile_snapshot(
                snap_id, 2, "postgresql://fake",
                supabase_url="https://supa.example", service_role_key="svc-key",
                portal_callback_url="https://cb.example", callback_secret="sec",
            )
        mock_dl.assert_called_once()
        self.assertEqual(mock_read.call_args.kwargs["season"], "spring")

    def test_excel_mode_fails_when_workbook_missing(self):
        with mock.patch.object(
            sys, "argv", ["sync_faculty_to_supabase.py", "--mode", "excel", "--excel", "/tmp/does-not-exist-9999.xlsx"]
        ):
            with self.assertRaises(SystemExit) as ctx:
                sfs.main()
            self.assertNotEqual(ctx.exception.code, 0)


class TestHardeningEdgeCasesAndRegressions(unittest.TestCase):
    def test_token_json_malformed_and_no_refresh_token_ci_vs_local(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tok = Path(tmpdir) / "token.json"
            cred = Path(tmpdir) / "credentials.json"
            cred.write_text('{"installed":{"client_id":"c"}}', encoding="utf-8")

            # 1. Malformed token.json in CI -> OAUTH_TOKEN_EXPIRED without InstalledAppFlow
            tok.write_text("{corrupt json", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CI": "true"}, clear=False), mock.patch.object(
                databaseHandler.InstalledAppFlow, "from_client_secrets_file"
            ) as mock_flow:
                with self.assertRaises(RuntimeError) as ctx:
                    databaseHandler.get_sheets_service(token_path=tok, credentials_path=cred)
            self.assertIn("OAUTH_TOKEN_EXPIRED", str(ctx.exception))
            mock_flow.assert_not_called()

            # 2. Expired token without refresh_token in CI -> OAUTH_TOKEN_EXPIRED
            tok.write_text('{"token":"x"}', encoding="utf-8")
            fake_creds_no_rt = mock.MagicMock(valid=False, expired=True, refresh_token=None)
            with mock.patch.dict(os.environ, {"CI": "true"}, clear=False), mock.patch.object(
                databaseHandler.Credentials, "from_authorized_user_file", return_value=fake_creds_no_rt
            ), mock.patch.object(databaseHandler.InstalledAppFlow, "from_client_secrets_file") as mock_flow:
                with self.assertRaises(RuntimeError) as ctx2:
                    databaseHandler.get_sheets_service(token_path=tok, credentials_path=cred)
            self.assertIn("OAUTH_TOKEN_EXPIRED", str(ctx2.exception))
            mock_flow.assert_not_called()

            # 3. TransportError on refresh in CI -> OAUTH_TOKEN_EXPIRED
            fake_creds_rt = mock.MagicMock(valid=False, expired=True, refresh_token="r")
            fake_creds_rt.refresh.side_effect = TransportError("network down")
            with mock.patch.dict(os.environ, {"CI": "true"}, clear=False), mock.patch.object(
                databaseHandler.Credentials, "from_authorized_user_file", return_value=fake_creds_rt
            ):
                with self.assertRaises(RuntimeError) as ctx3:
                    databaseHandler.get_sheets_service(token_path=tok, credentials_path=cred)
            self.assertIn("OAUTH_TOKEN_EXPIRED", str(ctx3.exception))

            # 4. Malformed token.json locally (CI unset) -> interactive OAuth fallback
            tok.write_text("{corrupt json", encoding="utf-8")
            fresh_creds = mock.MagicMock(valid=True)
            fresh_creds.to_json.return_value = '{"token":"fresh"}'
            fake_flow = mock.MagicMock()
            fake_flow.run_local_server.return_value = fresh_creds
            env_no_ci = {k: v for k, v in os.environ.items() if k not in ("CI", "GITHUB_ACTIONS")}
            with mock.patch.dict(os.environ, env_no_ci, clear=True), mock.patch.object(
                databaseHandler.InstalledAppFlow, "from_client_secrets_file", return_value=fake_flow
            ) as mock_flow, mock.patch.object(databaseHandler, "build", return_value="svc"):
                svc = databaseHandler.get_sheets_service(token_path=tok, credentials_path=cred)
            self.assertEqual(svc, "svc")
            mock_flow.assert_called_once()
            fake_flow.run_local_server.assert_called_once()

    def test_rebuild_db_preserves_existing_dbs_on_midbuild_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            t_db = os.path.join(tmpdir, "t.db")
            l_db = os.path.join(tmpdir, "l.db")
            with open(t_db, "wb") as f:
                f.write(b"ORIGINAL_THEORY_DB")
            with open(l_db, "wb") as f:
                f.write(b"ORIGINAL_LAB_DB")

            with mock.patch.object(
                rebuild_db, "get_active_spreadsheet_id", return_value=("2027-spring", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD")
            ), mock.patch.object(rebuild_db, "get_sheets_service"), mock.patch.object(
                rebuild_db, "get_day_sheet_mapping", return_value={"Monday": "Monday"}
            ), mock.patch.object(
                rebuild_db, "read_and_clean_classroom_df", side_effect=RuntimeError("mid-build failure")
            ):
                with self.assertRaises(RuntimeError):
                    rebuild_db.rebuild(course_db=t_db, lab_db=l_db, skip_static_gen=True)

            with open(t_db, "rb") as f:
                self.assertEqual(f.read(), b"ORIGINAL_THEORY_DB")
            with open(l_db, "rb") as f:
                self.assertEqual(f.read(), b"ORIGINAL_LAB_DB")
            self.assertEqual(sorted(os.listdir(tmpdir)), ["l.db", "t.db"])

    def test_sheets_subject_extractor_and_evening_legend_guards(self):
        fake_svc = mock.MagicMock()
        fake_svc.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"data": [{"rowData": []}]}]
        }
        with mock.patch.object(
            sheets_subject_extractor, "get_active_spreadsheet_id", return_value=("2027-spring", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD")
        ), mock.patch.object(sheets_subject_extractor, "get_sheets_service", return_value=fake_svc), mock.patch.object(
            sheets_subject_extractor, "get_day_sheet_mapping", return_value={"Monday": "Monday"}
        ):
            with self.assertRaises(RuntimeError) as ctx:
                sheets_subject_extractor.extract_subjects_and_batches_from_api()
        self.assertIn("SHEET_STRUCTURE_INVALID", str(ctx.exception))

        # Evening legend stops before Room header row and tolerates formattedValue=None
        row_data = [
            {"values": [{}, {"formattedValue": "Evening MS CS", "effectiveFormat": {"backgroundColor": {"red": 0.4, "green": 0.5, "blue": 0.6}}}]},
            {"values": [{"formattedValue": "Room"}, {"formattedValue": None}]},
            {"values": [{}, {"formattedValue": "Body Course (BCS-2A)", "effectiveFormat": {"backgroundColor": {"red": 0.1, "green": 0.2, "blue": 0.3}}}]},
        ]
        self.assertEqual(sheets_to_df._find_first_room_header_row(row_data), 1)
        legend = sheets_to_df._extract_evening_legend(row_data, evening_start_col=1)
        self.assertEqual(legend[(102, 128, 153)], "Evening MS CS")
        self.assertNotIn((26, 51, 77), legend)

    def test_generate_static_json_ignores_bin_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subj_db = os.path.join(tmpdir, "subjects.db")
            course_db = os.path.join(tmpdir, "course.db")
            lab_db = os.path.join(tmpdir, "lab.db")
            out_dir = os.path.join(tmpdir, "out")
            sched_dir = os.path.join(out_dir, "schedules")
            dir_bin = os.path.join(sched_dir, "keep_dir.bin")
            os.makedirs(dir_bin, exist_ok=True)
            stale_file = os.path.join(sched_dir, "stale.bin")
            with open(stale_file, "w", encoding="utf-8") as f:
                f.write("stale")

            with closing(sqlite3.connect(subj_db)) as c_s:
                c_s.execute("CREATE TABLE batches (id INTEGER PRIMARY KEY, name TEXT, color_hex TEXT)")
                c_s.execute("CREATE TABLE subjects (id INTEGER PRIMARY KEY, name TEXT, short_name TEXT)")
                c_s.execute("CREATE TABLE batch_subjects (id INTEGER PRIMARY KEY, batch_id INTEGER, subject_id INTEGER)")
                c_s.commit()
            with closing(sqlite3.connect(course_db)) as c_c:
                c_c.execute("CREATE TABLE timetable (ID INTEGER PRIMARY KEY, DAY TEXT, START_TIME TEXT, END_TIME TEXT, SUBJECT TEXT, CLASSROOM TEXT, SECTION TEXT, BATCH TEXT, STATUS TEXT)")
                c_c.commit()
            with closing(sqlite3.connect(lab_db)) as c_l:
                c_l.execute("CREATE TABLE timetable (ID INTEGER PRIMARY KEY, DAY TEXT, START_TIME TEXT, END_TIME TEXT, SUBJECT TEXT, LAB TEXT, SECTION TEXT, BATCH TEXT, STATUS TEXT)")
                c_l.commit()

            with mock.patch.object(generate_static_json, "SUBJECTS_DB", subj_db), mock.patch.object(
                generate_static_json, "COURSE_DB", course_db
            ), mock.patch.object(generate_static_json, "LAB_DB", lab_db), mock.patch.object(
                generate_static_json, "OUTPUT_DIR", out_dir
            ):
                generate_static_json.generate_static_data()

            self.assertFalse(os.path.exists(stale_file))
            self.assertTrue(os.path.isdir(dir_bin))

    def test_reconcile_json_string_schedule_and_case_email_dedup(self):
        conn_t = sqlite3.connect(":memory:")
        conn_t.row_factory = sqlite3.Row
        conn_t.execute("CREATE TABLE timetable (ID INTEGER PRIMARY KEY, DAY TEXT, START_TIME TEXT, END_TIME TEXT, SUBJECT TEXT, CLASSROOM TEXT, SECTION TEXT, BATCH TEXT, STATUS TEXT)")
        conn_t.execute("INSERT INTO timetable VALUES (1, 'Monday', '08:30', '09:50', 'OOP', 'C-301', 'CS-A', 'BS 26 CS', NULL)")
        conn_l = sqlite3.connect(":memory:")
        conn_l.row_factory = sqlite3.Row
        conn_l.execute("CREATE TABLE timetable (ID INTEGER PRIMARY KEY, DAY TEXT, START_TIME TEXT, END_TIME TEXT, SUBJECT TEXT, LAB TEXT, SECTION TEXT, BATCH TEXT, STATUS TEXT)")
        conn_l.execute("INSERT INTO timetable VALUES (1, 'Monday', '08:30', '09:50', 'OOP', 'Rawal-1', 'CS-B', 'BS 26 CS', NULL)")

        rows = [
            {
                "email": "Test.Prof@nu.edu.pk",
                "semester_id": "2027-spring",
                "name": "Prof Test",
                "designation": "AP",
                "department": "CS",
                "office": "C-101",
                "schedule": json.dumps({"Monday": [{"subject": "OOP", "section": "CS-A", "batch": "BS 26 CS", "is_lab": False}]}),
                "courses": json.dumps([{"course_code": "CS1002", "course_name": "OOP", "canonical_subject": "OOP", "sections": ["BCS-2A"], "is_lab": False}]),
                "total_credit_hours": 3.0,
            },
            {
                "email": "test.prof@nu.edu.pk",
                "semester_id": "2027-spring",
                "name": "Prof Test",
                "designation": "AP",
                "department": "CS",
                "office": "C-101",
                "schedule": {},
                "courses": [{"course_code": "CL1002", "course_name": "OOP Lab", "canonical_subject": "OOP", "sections": ["BCS-2B"], "is_lab": True}],
                "total_credit_hours": 1.0,
            },
        ]
        try:
            reconciled = sfs.reconcile_existing_db_rows(
                rows, conn_t.cursor(), conn_l.cursor(), semester_id="2027-spring", year=2027, season="Spring"
            )
        finally:
            conn_t.close()
            conn_l.close()

        # Deduplicated to 1 record and theory/lab at same time stay distinct slots
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["email"], "test.prof@nu.edu.pk")
        monday_slots = reconciled[0]["schedule"]["Monday"]
        self.assertEqual(len(monday_slots), 2)
        self.assertEqual({bool(s["is_lab"]) for s in monday_slots}, {True, False})

        # Unsorted comma-separated initial section order matches sorted merge order
        w1 = {d: [] for d in sfs.DAYS_OF_WEEK}
        w2 = {d: [] for d in sfs.DAYS_OF_WEEK}
        row_unsorted = {"DAY": "Monday", "START_TIME": "10:00", "END_TIME": "11:20", "SUBJECT": "OOP", "LOCATION": "C-301", "SECTION": "CS-B, CS-A", "BATCH": "BS 26 CS", "STATUS": None}
        row_sorted = dict(row_unsorted, SECTION="CS-A, CS-B")
        sfs._merge_slot_into_weekly_schedule(w1, row_unsorted, "CS1002", "OOP", "CS-B, CS-A", "BS 26 CS", False, semester_id="2027-spring")
        sfs._merge_slot_into_weekly_schedule(w2, row_sorted, "CS1002", "OOP", "CS-A, CS-B", "BS 26 CS", False, semester_id="2027-spring")
        self.assertEqual(w1["Monday"][0]["slot_uid"], w2["Monday"][0]["slot_uid"])
        self.assertEqual(w1["Monday"][0]["section"], "CS-A, CS-B")

    def test_zip_boundaries_and_backslash_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 500 entries allowed; 501 rejected
            ok_zip = os.path.join(tmpdir, "ok500.xlsx")
            with zipfile.ZipFile(ok_zip, "w") as zf:
                for i in range(500):
                    zf.writestr(f"xl/f_{i}.xml", "a")
            sfs.validate_xlsx_zip_safety(ok_zip)

            too_many = os.path.join(tmpdir, "bad501.xlsx")
            with zipfile.ZipFile(too_many, "w") as zf:
                for i in range(501):
                    zf.writestr(f"xl/f_{i}.xml", "a")
            with self.assertRaises(sfs.JobError) as ctx:
                sfs.validate_xlsx_zip_safety(too_many)
            self.assertEqual(ctx.exception.error_code, "ZIP_BOMB_DETECTED")

            # Backslash traversal rejected
            backslash_zip = os.path.join(tmpdir, "win_trav.xlsx")
            with zipfile.ZipFile(backslash_zip, "w") as zf:
                zf.writestr("..\\..\\etc\\passwd", "nope")
            with self.assertRaises(sfs.JobError) as ctx2:
                sfs.validate_xlsx_zip_safety(backslash_zip)
            self.assertEqual(ctx2.exception.error_code, "INVALID_XLSX")

    def test_claim_job_type_isolation_and_marker_files(self):
        seen_params = []

        def claim_handler(op, sql, params, cur):
            if op == "execute" and "UPDATE public.ingestion_jobs" in sql:
                seen_params.append((sql, params))
                return [{"id": "11111111-1111-1111-1111-111111111111", "semester_id": "2027-spring"}]
            return []

        with mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(claim_handler)):
            sfs._claim_ingestion_job("postgresql://fake", "11111111-1111-1111-1111-111111111111", expected_job_types=("NEW_DRAFT", "RETRY_JOB"))
            sfs._claim_ingestion_job("postgresql://fake", "11111111-1111-1111-1111-111111111111", expected_job_types=("REFRESH_DRAFT_SHEET",))

        self.assertIn("job_type = ANY(%s)", seen_params[0][0])
        self.assertEqual(seen_params[0][1][2], ["NEW_DRAFT", "RETRY_JOB"])
        self.assertEqual(seen_params[1][1][2], ["REFRESH_DRAFT_SHEET"])

        # Marker written on _mark_job_failed and send_sync_callback
        with tempfile.TemporaryDirectory() as tmpdir:
            ingest_marker = os.path.join(tmpdir, "ingest.marker")
            cb_marker = os.path.join(tmpdir, "cb.marker")
            with mock.patch.dict(os.environ, {"INGEST_FAIL_MARKER_PATH": ingest_marker, "SYNC_CB_MARKER_PATH": cb_marker}, clear=False):
                with mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(lambda *args: [])):
                    sfs._mark_job_failed("postgresql://fake", "11111111-1111-1111-1111-111111111111", "INTERNAL_ERROR", "boom")
                fake_resp = mock.MagicMock(ok=True)
                fake_resp.json.return_value = {"ok": True}
                with mock.patch.object(sfs.requests, "post", return_value=fake_resp):
                    sfs.send_sync_callback("faculty_sync_callback", "2027-spring", 1, "SYNCED", None, "https://cb.example", "sec")
            self.assertTrue(os.path.exists(ingest_marker))
            self.assertTrue(os.path.exists(cb_marker))

    def test_reconcile_snapshot_rows_fallback_status_and_prechecks(self):
        snap_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCD"

        # 1. Draft / Discarded snapshot rejected before building sheets
        for bad_status in ("DRAFT", "DISCARDED"):
            def bad_status_db(op, sql, params, cur, st=bad_status):
                if op == "execute" and "FROM public.semester_snapshots ss" in sql:
                    return [{
                        "id": snap_id, "semester_id": "2027-spring", "status": st,
                        "snap_sheet_id": sheet_id, "sem_sheet_id": sheet_id,
                        "parsed_allocations": None, "allocation_storage_path": None,
                        "academic_year": 2027, "season": "Spring",
                        "state_version": 2, "is_published": True, "deleted_at": None,
                    }]
                return []

            with mock.patch.object(sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(bad_status_db)), mock.patch.object(
                sfs, "send_sync_callback"
            ) as mock_cb:
                with self.assertRaises(sfs.JobError) as ctx:
                    sfs.run_reconcile_snapshot(
                        snap_id, 2, "postgresql://fake", portal_callback_url="https://cb.example", callback_secret="sec"
                    )
            self.assertEqual(ctx.exception.error_code, "INVALID_SNAPSHOT_STATUS")
            mock_cb.assert_called_once()
            self.assertEqual(mock_cb.call_args.kwargs["status"], "FAILED")

        # 2. semester_snapshot_rows fallback & missing callback secret aborts before upsert commit
        def rows_fallback_db(op, sql, params, cur):
            if op == "execute" and "FROM public.semester_snapshots ss" in sql:
                return [{
                    "id": snap_id, "semester_id": "2027-spring", "status": "ROLLED_BACK",
                    "snap_sheet_id": sheet_id, "sem_sheet_id": sheet_id,
                    "parsed_allocations": None, "allocation_storage_path": None,
                    "academic_year": 2027, "season": "Spring",
                    "state_version": 2, "is_published": True, "deleted_at": None,
                }]
            if op == "execute" and "FROM public.semester_snapshot_rows" in sql:
                return [{
                    "email": "test@nu.edu.pk", "semester_id": "2027-spring", "name": "Prof",
                    "designation": "AP", "department": "CS", "office": "C-101",
                    "schedule": {"Monday": []}, "courses": [], "schedule_hash": "h", "total_credit_hours": 0.0,
                }]
            return []

        def init_tmp_dbs(sid, course_db, lab_db, **kwargs):
            with closing(sqlite3.connect(course_db)) as c_t:
                c_t.execute("CREATE TABLE timetable (ID INTEGER PRIMARY KEY, DAY TEXT, START_TIME TEXT, END_TIME TEXT, SUBJECT TEXT, CLASSROOM TEXT, SECTION TEXT, BATCH TEXT, STATUS TEXT)")
                c_t.commit()
            with closing(sqlite3.connect(lab_db)) as c_l:
                c_l.execute("CREATE TABLE timetable (ID INTEGER PRIMARY KEY, DAY TEXT, START_TIME TEXT, END_TIME TEXT, SUBJECT TEXT, LAB TEXT, SECTION TEXT, BATCH TEXT, STATUS TEXT)")
                c_l.commit()

        env_no_cb = {k: v for k, v in os.environ.items() if k not in ("PORTAL_CALLBACK_URL", "SYNC_CALLBACK_SECRET")}
        with mock.patch.dict(os.environ, env_no_cb, clear=True), mock.patch.object(
            sfs.psycopg2, "connect", side_effect=lambda *a, **k: FakeConn(rows_fallback_db)
        ), mock.patch("rebuild_db.build_sqlite_from_google_sheet", side_effect=init_tmp_dbs), mock.patch.object(
            sfs, "upsert_via_psycopg2"
        ) as mock_upsert:
            with self.assertRaises(sfs.JobError) as ctx_cb:
                sfs.run_reconcile_snapshot(snap_id, 2, "postgresql://fake")
        self.assertEqual(ctx_cb.exception.error_code, "MISSING_CALLBACK_CONFIG")
        mock_upsert.assert_not_called()

    def test_sync_yml_marker_fail_safe_and_rebuild_subjects_closes_handles(self):
        yml_path = os.path.join(ROOT_DIR, ".github", "workflows", "sync.yml")
        with open(yml_path, "r", encoding="utf-8") as f:
            content = f.read()
        for expected in (
            "INGEST_FAIL_MARKER_PATH: /tmp/ingest_job_marked",
            "SYNC_CB_MARKER_PATH: /tmp/faculty_cb_sent",
            "[ ! -f /tmp/ingest_job_marked ]",
            'os.path.exists("/tmp/faculty_cb_sent")',
        ):
            self.assertIn(expected, content)

        with tempfile.TemporaryDirectory() as tmpdir:
            subj_db = Path(tmpdir) / "subjects.db"
            course_db = Path(tmpdir) / "t.db"
            with closing(sqlite3.connect(course_db)) as c_t:
                c_t.execute("CREATE TABLE timetable (DAY TEXT, SUBJECT TEXT, BATCH TEXT)")
                c_t.execute("INSERT INTO timetable VALUES ('Monday', 'OOP', 'BS 26 CS')")
                c_t.commit()

            with mock.patch.object(rebuild_subjects, "DB_FILE", subj_db), mock.patch.object(
                rebuild_subjects, "TIMETABLE_DBS", [str(course_db)]
            ), mock.patch.object(
                rebuild_subjects, "extract_subjects_and_batches_from_api",
                return_value=([{"name": "BS 26 CS", "hex": "#000000"}], {"OOP": "OOP"}, [("BS 26 CS", "OOP")]),
            ):
                rebuild_subjects.rebuild_subjects_db()
            self.assertTrue(subj_db.exists())


if __name__ == "__main__":
    unittest.main()
