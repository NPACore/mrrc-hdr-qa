#!/usr/bin/env python3
import os
import sys
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

# --------- Config ---------
DEFAULT_PATTERN = os.environ.get("MRQART_PATTERN", "RewardedAnti")

BASE_DIR = Path(__file__).resolve().parent.parent
EMAIL_TOML = BASE_DIR / "config" / "email_settings.toml"
DB_PATH = Path(os.environ.get("MRQART_DB", BASE_DIR / "db.sqlite"))

try:
    import tomllib as toml  # py3.11+
except Exception:
    import toml  # type: ignore

from mrqart.acq2sqlite import DBQuery, none_to_null
from mrqart.template_checker import TemplateChecker


# --------- Helpers ---------
def load_email_entries(toml_path: Path) -> List[Dict[str, str]]:
    if not toml_path.exists():
        raise FileNotFoundError(f"Missing TOML: {toml_path}")
    cfg = toml.load(toml_path.open("rb"))
    entries: List[Dict[str, str]] = []
    for e in cfg.get("emails", []):
        sender = e.get("from")
        tos = e.get("to", [])
        if isinstance(tos, str):
            tos = [t.strip() for t in tos.split(",") if t.strip()]
        if not sender or not tos:
            continue
        for addr in tos:
            entries.append({"from": sender, "to": addr})
    return entries


def send_via_local_mail(subject: str, body: str, recipient: str) -> bool:
    try:
        proc = subprocess.run(
            ["mail", "-s", subject, recipient],
            input=body.encode("utf-8"),
            check=True,
        )
        return proc.returncode == 0
    except Exception as e:
        print(f"[warn] local mail send failed to {recipient}: {e}", file=sys.stderr)
        return False


def fetch_latest_row_for_pattern(conn: sqlite3.Connection, pattern_like: str) -> Optional[sqlite3.Row]:
    """
    Return the most recent acquisition row joined with its acq_param,
    filtered by SequenceName LIKE %pattern_like%.
    """
    like = pattern_like if "%" in pattern_like else f"%{pattern_like}%"
    q = """
        SELECT
          a.*,                 -- variable fields (AcqDate, AcqTime, SeriesNumber, SubID, Operator, Station, Shims)
          p.*                  -- invariant fields (Project, SequenceName, TR, TE, FA, etc.)
        FROM acq a
        JOIN acq_param p ON a.param_id = p.rowid
        WHERE p.SequenceName LIKE ?
        ORDER BY (a.AcqDate || ' ' || a.AcqTime) DESC
        LIMIT 1
    """
    cur = conn.execute(q, (like,))
    row = cur.fetchone()
    return none_to_null(row)


def fetch_with_backoffs(conn: sqlite3.Connection, pattern: str) -> tuple[Optional[sqlite3.Row], List[str]]:
    """
    Try progressively looser patterns:
      1) as-is
      2) strip suffix after first underscore
      3) known variants: 'RewardedAntisaccade', 'RewardedAnti'
    Returns (row, tried_patterns)
    """
    tried: List[str] = []

    def try_pat(p: str) -> Optional[sqlite3.Row]:
        if p in tried:
            return None
        tried.append(p)
        return fetch_latest_row_for_pattern(conn, p)

    # 1) exact-ish (LIKE with wildcards)
    row = try_pat(pattern)
    if row:
        return row, tried

    # 2) strip suffix after first underscore (e.g., '_704x75')
    if "_" in pattern:
        base = pattern.split("_", 1)[0]
        row = try_pat(base)
        if row:
            return row, tried

    # 3) known variants (order matters—most specific first)
    for variant in ("RewardedAntisaccade", "RewardedAnti"):
        row = try_pat(variant)
        if row:
            return row, tried

    return None, tried


def row_to_hdr_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """
    Convert the joined acq+acq_param row into the header dict shape expected by TemplateChecker.
    """
    d = dict(row) if row is not None else {}
    for k, v in list(d.items()):
        if isinstance(v, str):
            d[k] = v.replace("\t", " ").replace("\n", " ").strip()
    return d


def compose_email_body(
    pattern: str,
    check: Dict[str, Any],
    row: Optional[sqlite3.Row],
    db_used: str,
) -> str:
    conforms = check.get("conforms", False)
    errors = check.get("errors", {}) or {}
    err_count = len(errors)
    err_text = "\n".join([f" - {k}: expect={v['expect']} have={v['have']}" for k, v in errors.items()]) or " - None"

    hdr = check.get("input", {}) or {}
    project = hdr.get("Project", "N/A")
    seqname = hdr.get("SequenceName", "N/A")
    fa = hdr.get("FA", "N/A")
    station = hdr.get("Station", "N/A")
    series = hdr.get("SeriesNumber", "N/A")

    when = "N/A"
    if row is not None:
        try:
            when = f"{row['AcqDate']} {row['AcqTime']}"
        except Exception:
            pass

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body = (
        "Header compliance check for latest scan (from DB)\n"
        f"Pattern (SequenceName LIKE): {pattern}\n"
        f"Project: {project}\n"
        f"Sequence: {seqname}\n"
        f"Conforms: {'True' if conforms else 'False'}\n"
        f"Errors ({err_count}):\n{err_text}\n\n"
        f"Flip Angle (FA): {fa}\n"
        f"Station: {station}\n"
        f"SeriesNumber: {series}\n"
        f"Acq timestamp (DB): {when}\n\n"
        f"Timestamp (script): {now}\n"
        f"(DB used: {db_used})\n"
        "— MRQART\n"
    )
    return body


def main() -> int:
    pattern = DEFAULT_PATTERN

    # recipients
    try:
        email_entries = load_email_entries(EMAIL_TOML)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    if not email_entries:
        print(f"[error] No usable recipients in {EMAIL_TOML}", file=sys.stderr)
        return 2

    # DB connect
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
    except Exception as e:
        print(f"[error] cannot open DB {DB_PATH}: {e}", file=sys.stderr)
        return 2

    # Fetch the most recent matching acquisition (with fallbacks)
    row, tried = fetch_with_backoffs(conn, pattern)
    if not row:
        print(
            f"[error] No recent acquisitions for SequenceName LIKE any of: "
            + ", ".join([f"'%{p}%'" for p in tried]),
            file=sys.stderr,
        )
        conn.close()
        return 3

    # Build current header dict from DB row
    hdr = row_to_hdr_dict(row)

    # Official conformance check (uses tolerant string compare you added)
    checker = TemplateChecker(db=conn, context="RT")
    check = checker.check_header(hdr)

    conforms_str = "True" if check.get("conforms") else "False"
    subject = f"MRQART: Latest {pattern} — conforms={conforms_str} — errors={len(check.get('errors', {}))}"
    body = compose_email_body(pattern, check, row, str(DB_PATH))

    any_fail = False
    for e in email_entries:
        ok = send_via_local_mail(subject, body, e["to"])
        if ok:
            print(f"[ok] mailed {e['to']}")
        else:
            any_fail = True

    conn.close()
    return 0 if not any_fail else 7


if __name__ == "__main__":
    raise SystemExit(main())

