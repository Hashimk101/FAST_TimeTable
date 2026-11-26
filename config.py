"""
config.py
=========
Centralized active semester and Google Spreadsheet resolution for TimeTable_Maker.

Resolution order:
1. Explicit override (`override_id`) validated against `^[a-zA-Z0-9_-]{20,128}$`.
2. Authoritative Supabase PostgreSQL query via `DATABASE_URL` against `public.semesters`.
3. Offline `.env` fallback (`SPREADSHEET_ID`) ONLY when `CI != "true"` and `DATABASE_URL` is absent.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DOTENV_PATH = BASE_DIR / ".env"
SHEET_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{20,128}$")


class ConfigError(RuntimeError):
    """Raised when active semester or spreadsheet resolution fails closed."""


def is_ci_environment() -> bool:
    """Returns True when running in CI (`CI=true`), enforcing strict fail-closed behavior."""
    return os.environ.get("CI", "").strip().lower() == "true"


def validate_spreadsheet_id(sheet_id: str) -> str:
    """Validates a Google Spreadsheet ID against `^[a-zA-Z0-9_-]{20,128}$`."""
    cleaned = str(sheet_id or "").strip()
    if not SHEET_ID_PATTERN.fullmatch(cleaned):
        raise ValueError(f"Invalid Google Spreadsheet ID: {sheet_id!r}")
    return cleaned


def _read_dotenv_file(dotenv_path: Path) -> Dict[str, str]:
    """Parses key=value pairs from a local .env file without mutating os.environ."""
    values: Dict[str, str] = {}
    if not dotenv_path.exists():
        return values
    with open(dotenv_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and ((val[0] == val[-1] == "'") or (val[0] == val[-1] == '"')):
                val = val[1:-1]
            values[key] = val
    return values


def get_database_url(dotenv_path: Optional[Path] = None) -> Optional[str]:
    """Returns DATABASE_URL from env (or local .env ONLY when CI != 'true')."""
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if db_url:
        return db_url
    if is_ci_environment():
        return None
    env_map = _read_dotenv_file(dotenv_path or DEFAULT_DOTENV_PATH)
    local_url = (env_map.get("DATABASE_URL") or "").strip()
    return local_url or None


def get_active_semester_config(
    override_id: Optional[str] = None,
    dotenv_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Resolves active semester metadata and Google Spreadsheet ID.

    Returns dict with keys:
      semester_id, google_sheet_id, academic_year, season, sync_policy, state_version
    """
    # 1. Explicit Override First
    if override_id is not None:
        valid_override = validate_spreadsheet_id(override_id)
        return {
            "semester_id": None,
            "google_sheet_id": valid_override,
            "academic_year": None,
            "season": None,
            "sync_policy": None,
            "state_version": None,
        }

    # 2. Authoritative Supabase Query Second
    ci_mode = is_ci_environment()
    database_url = get_database_url(dotenv_path=dotenv_path)

    if database_url:
        if not HAS_PSYCOPG2:
            raise ConfigError("psycopg2 is required to query active semester configuration via DATABASE_URL.")
        conn = None
        cursor = None
        try:
            conn = psycopg2.connect(database_url)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, google_sheet_id, academic_year, season, sync_policy, state_version
                FROM public.semesters
                WHERE is_active = true AND is_published = true AND deleted_at IS NULL
                ORDER BY updated_at DESC
                LIMIT 1;
                """
            )
            row = cursor.fetchone()
        except Exception as exc:
            raise ConfigError(f"Failed to query active semester from Supabase: {exc}") from exc
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()

        if not row:
            raise ConfigError(
                "No active, published, non-deleted semester row found in public.semesters."
            )

        sem_id, raw_sheet_id, academic_year, season, sync_policy, state_version = row
        try:
            valid_sheet_id = validate_spreadsheet_id(raw_sheet_id or "")
        except ValueError as exc:
            raise ConfigError(
                f"Active semester '{sem_id}' has invalid or missing google_sheet_id."
            ) from exc

        return {
            "semester_id": str(sem_id),
            "google_sheet_id": valid_sheet_id,
            "academic_year": int(academic_year) if academic_year is not None else None,
            "season": str(season).strip() if season is not None else "Fall",
            "sync_policy": str(sync_policy).strip() if sync_policy is not None else "AUTO_ENABLED",
            "state_version": int(state_version) if state_version is not None else 1,
        }

    # 3. Offline .env Fallback ONLY Locally (Fail Closed in CI)
    if ci_mode:
        raise ConfigError(
            "DATABASE_URL is missing in CI=true environment; refusing local .env or stale fallback."
        )

    env_map = _read_dotenv_file(dotenv_path or DEFAULT_DOTENV_PATH)
    local_sheet = (
        os.environ.get("SPREADSHEET_ID")
        or env_map.get("SPREADSHEET_ID")
        or ""
    ).strip()
    if not local_sheet:
        raise ConfigError(
            "DATABASE_URL is unset and no local SPREADSHEET_ID was found in .env."
        )

    valid_local_sheet = validate_spreadsheet_id(local_sheet)
    return {
        "semester_id": None,
        "google_sheet_id": valid_local_sheet,
        "academic_year": None,
        "season": None,
        "sync_policy": None,
        "state_version": None,
    }


def get_active_spreadsheet_id(
    override_id: Optional[str] = None,
    dotenv_path: Optional[Path] = None,
) -> Tuple[Optional[str], str]:
    """Returns `(semester_id, google_sheet_id)` using the centralized resolution policy."""
    cfg = get_active_semester_config(override_id=override_id, dotenv_path=dotenv_path)
    return cfg.get("semester_id"), cfg["google_sheet_id"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Resolve active semester config.")
    parser.add_argument("--override-id", type=str, default=None, help="Explicit Google Sheet ID override")
    parser.add_argument("--json", action="store_true", help="Print resolved config as JSON")
    args = parser.parse_args()

    try:
        resolved = get_active_semester_config(override_id=args.override_id)
    except Exception as err:
        print(f"[ERROR] {err}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(resolved))
    else:
        for k, v in resolved.items():
            print(f"{k}={v}")
