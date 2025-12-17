#!/usr/bin/env python3
"""
Daily header-compliance summary email based on db.sqlite.

- Looks at acquisitions with AcqDate = yesterday (or MRQART_DATE override).
- Rebuilds template_by_count each run from make_template_by_count.sql.
- Uses acq2sqlite.DBQuery templates (template_by_count + acq_param).
- Groups by (Project, SequenceName).
- Skips SeriesNumber > 200; formats SeriesNumber as %03d.
- Reports non-conforming acquisitions (marquee cols) and missing templates split by onboarding state.
- Optional logging:
  - MRQART_LOG=1 appends run info to logs/mrqart_daily.log
  - MRQART_LOG_PATH can override the log file path
  - MRQART_DEBUG=1 prints debug to stderr
"""

from __future__ import annotations

import os
import sys
import sqlite3
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .acq2sqlite import DBQuery

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "db.sqlite"
EMAIL_TOML = BASE_DIR / "config" / "email_settings.toml"
TEMPLATE_SQL = BASE_DIR / "make_template_by_count.sql"
DEFAULT_LOG_PATH = BASE_DIR / "logs" / "mrqart_daily.log"

INTERESTING_SUBSTRINGS: List[str] = [
    "rewardedanti",
    "abcd",
    "t1",
    "vnav",
]

BLACKLIST_SEQTYPE_PREFIXES: List[str] = [
    # High-frequency EPI / spin-echo types
    "epfid2d1",
    "epfid2d3",
    "epse2d1",
    "ep",
    "*epfid2d1",
    "*ep",

    # Common 3D/2D gradient sequences and scouts
    "*tfl3d1",
    "tfl3d1",
    "tfl2d1",
    "*fl2d1",
    "fl2d1",
    "*fl3d1",
    "*fl3d1r",
    "*fl3d2",
    "*fl3d4",
    "*fl3d5",
    "*fl3d5r",
    "*fl3d6",
    "*fl3d6r",
    "fl3d2r",
    "*fldyn3d1",

    # Field maps and SWI variants
    "*fm2d2r",
    "fm2d2",
    "fm2d3",
    "fm2d5",
    "swi3d2r",
    "*swi3d2r",
    "*swi3d1r",

    # TSE / inversion recovery variants
    "*tse2d1",
    "tse2d1",
    "*tse2d1rr13",
    "*tse2d1rr32",
    "*qtse2d1",
    "*qtir2d1",
    "*tir2d1",

    # MP2RAGE / SPC families and related
    "*spc",
    "spc3d1",
    "spc",
    "*spcr",
    "*spcrrr80",

    # Other common sequences
    "afi3d3",
    "mbpcasl2d1",
    "*tgse3d1",
    "tgse3d1",
    "*h2d1",
    "wip",
]

MARQUEE_COLS: List[str] = [
    "PED_major",
    "iPAT",
    "TR",
    "TE",
    "Matrix",
    "FA",
    "FoV",
]

try:
    import tomllib as toml  # Python 3.11+
except Exception:
    import toml  # type: ignore


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _debug_enabled() -> bool:
    return os.environ.get("MRQART_DEBUG", "").strip() not in ("", "0", "false", "False")


def _log_enabled() -> bool:
    return os.environ.get("MRQART_LOG", "").strip() not in ("", "0", "false", "False")


def _log_path() -> Path:
    p = os.environ.get("MRQART_LOG_PATH", "").strip()
    return Path(p) if p else DEFAULT_LOG_PATH


def log_line(msg: str) -> None:
    if not _log_enabled():
        return
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{_now_iso()} {msg}\n")


def dbg(msg: str) -> None:
    if _debug_enabled():
        print(f"[mrqart] {msg}", file=sys.stderr)


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


def _as_float(x: Any) -> float | None:
    try:
        return float(x)
    except Exception:
        return None


def normalize_for_compare(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip().lower()
    if s in ("null", "none", ""):
        return ""
    return s


def parse_ta_seconds(val: Any) -> int | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    s = s.replace("TA", "").replace("ta", "").strip()
    s = s.replace(" ", "")
    if ":" not in s:
        return None
    parts = s.split(":")
    try:
        nums = [int(p) for p in parts]
    except Exception:
        return None
    if len(nums) == 2:
        mm, ss = nums
        return mm * 60 + ss
    if len(nums) == 3:
        hh, mm, ss = nums
        return hh * 3600 + mm * 60 + ss
    return None


def format_expected_got(col: str, exp: Any, got: Any) -> str:
    if col == "FA":
        ev, gv = _as_float(exp), _as_float(got)
        if ev is not None and gv is not None:
            d = gv - ev
            s = "+" if d > 0 else ""
            if abs(d) < 1e-6:
                return f"FA: expected {exp}, got {got}"
            return f"FA: expected {exp}, got {got} ({s}{d:g}°)"
        return f"FA: expected {exp}, got {got}"

    if col == "TA":
        es, gs = parse_ta_seconds(exp), parse_ta_seconds(got)
        if es is not None and gs is not None:
            d = gs - es
            s = "+" if d > 0 else ""
            if d == 0:
                return f"TA: expected {exp}, got {got}"
            return f"TA: expected {exp}, got {got} ({s}{d}s)"
        return f"TA: expected {exp}, got {got}"

    return f"{col}: expected {exp}, got {got}"


def compact_diff_list(errors: Dict[str, str], prefer_cols: List[str], max_items: int = 6) -> str:
    prefer = list(prefer_cols) + ["TA"]
    ordered: List[str] = []
    seen: set[str] = set()
    for k in prefer:
        if k in errors and k not in seen:
            ordered.append(k)
            seen.add(k)
    for k in sorted(errors.keys()):
        if k not in seen:
            ordered.append(k)
            seen.add(k)
    ordered = ordered[:max_items]
    return ", ".join(ordered) if ordered else "diff"


def compare_row_against_template(
    acq_param_row: sqlite3.Row,
    tmpl: Dict[str, Any],
    consts: List[str],
    marquee_cols: List[str],
) -> Tuple[Dict[str, str], bool]:
    errors: Dict[str, str] = {}
    marquee_mismatch = False
    marquee_set = set(marquee_cols)

    for col in consts:
        hdr_val = acq_param_row[col] if col in acq_param_row.keys() else None
        db_val = tmpl.get(col)

        hvf, dvf = _as_float(hdr_val), _as_float(db_val)
        mismatch = False

        if hvf is not None and dvf is not None:
            if abs(hvf - dvf) > 1e-3:
                mismatch = True
        else:
            hv_norm = normalize_for_compare(hdr_val)
            dv_norm = normalize_for_compare(db_val)
            if hv_norm != dv_norm:
                mismatch = True

        if mismatch:
            errors[col] = f"expected {db_val}, got {hdr_val}"
            if col in marquee_set:
                marquee_mismatch = True

    return errors, marquee_mismatch


def is_interesting_sequence_with_blacklist(project: str, seqname: str, seqtype: str | None) -> bool:
    sname = (seqname or "").lower()
    if INTERESTING_SUBSTRINGS and any(sub in sname for sub in INTERESTING_SUBSTRINGS):
        return True

    stype = (seqtype or "").lower()
    if stype and BLACKLIST_SEQTYPE_PREFIXES:
        prefix = stype.split("_", 1)[0]
        if prefix in [p.lower() for p in BLACKLIST_SEQTYPE_PREFIXES]:
            return False

    return True


def series_int(series: Any) -> int | None:
    try:
        return int(str(series).strip())
    except Exception:
        return None


def format_series_003(series: Any) -> str:
    si = series_int(series)
    if si is None:
        return str(series)
    return f"{si:03d}"


def series_is_posthoc(series: Any) -> bool:
    si = series_int(series)
    return (si is not None) and (si > 200)


def yyyymmdd_to_iso(s: Any) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    if len(t) == 8 and t.isdigit():
        return f"{t[0:4]}-{t[4:6]}-{t[6:8]}"
    return t or None


def get_templates_in_study(sql: sqlite3.Connection, project: str) -> int:
    row = sql.execute(
        "SELECT COUNT(*) FROM template_by_count WHERE Project = ?",
        (project,),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def first_seen_from_template_by_count(sql: sqlite3.Connection, project: str, seqname: str) -> str | None:
    row = sql.execute(
        """
        SELECT "first"
        FROM template_by_count
        WHERE Project = ? AND SequenceName = ?
        """,
        (project, seqname),
    ).fetchone()
    if not row or row[0] is None:
        return None
    return yyyymmdd_to_iso(row[0])


def first_seen_date_for_seq(sql: sqlite3.Connection, project: str, seqname: str) -> str | None:
    row = sql.execute(
        """
        SELECT MIN(a.AcqDate)
        FROM acq a
        JOIN acq_param p ON a.param_id = p.rowid
        WHERE p.Project = ? AND p.SequenceName = ?
        """,
        (project, seqname),
    ).fetchone()
    if not row or not row[0]:
        return None
    return yyyymmdd_to_iso(row[0])


def rebuild_templates(sql: sqlite3.Connection) -> None:
    if not TEMPLATE_SQL.exists():
        raise FileNotFoundError(f"Missing SQL: {TEMPLATE_SQL}")
    dbg(f"rebuilding template_by_count from {TEMPLATE_SQL.name}")
    sql.executescript(TEMPLATE_SQL.read_text())
    sql.commit()
    log_line("template_by_count rebuilt")


def main() -> int:
    db_path = Path(os.environ.get("MRQART_DB", DEFAULT_DB))
    sql = sqlite3.connect(str(db_path))
    sql.row_factory = sqlite3.Row

    rebuild_templates(sql)

    try:
        email_entries = load_email_entries(EMAIL_TOML)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    if not email_entries:
        print(f"[error] No usable recipients in {EMAIL_TOML}", file=sys.stderr)
        return 2

    db = DBQuery(sql)
    consts = DBQuery.CONSTS

    override = os.environ.get("MRQART_DATE")
    if override:
        override = override.strip()
        yday_str = override.replace("-", "") if "-" in override else override
        report_date = datetime.strptime(yday_str, "%Y%m%d")
    else:
        report_date = datetime.now() - timedelta(days=1)
        yday_str = report_date.strftime("%Y%m%d")

    acq_rows = sql.execute(
        """
        SELECT a.rowid AS acq_id,
               a.AcqDate, a.AcqTime, a.Station, a.SubID, a.SeriesNumber,
               p.*
        FROM acq a
        JOIN acq_param p ON a.param_id = p.rowid
        WHERE a.AcqDate = ?
        ORDER BY a.AcqDate, a.AcqTime, p.Project, p.SequenceName
        """,
        (yday_str,),
    ).fetchall()

    date_label = report_date.strftime("%Y-%m-%d")

    if not acq_rows:
        subject = "[MRQA] ✅ 0/0 (0); 0 MIA"
        body = (
            f"MRQART header compliance summary for {date_label}\n\n"
            "No acquisitions were found in the DB for this date.\n"
            "— MRQART\n"
        )
        any_fail = False
        for e in email_entries:
            ok = send_via_local_mail(subject, body, e["to"])
            if ok:
                print(f"[ok] mailed {e['to']}")
            else:
                any_fail = True
        log_line(f"run date={date_label} seen=0 checked=0 nonconf=0 mia=0 subject={subject!r}")
        return 0 if not any_fail else 7

    total_seen_today = len(acq_rows)

    seq_summary: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "nonconforming": 0,
            "anydiff": 0,
            "examples": [],
            "mismatch_counts": defaultdict(int),
        }
    )
    missing_templates: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "examples": [],
            "first_seen": None,
            "templates_in_study": 0,
            "study_count_today": 0,
            "seq_count_today": 0,
        }
    )

    total_checked = 0
    total_nonconforming = 0
    total_anydiff = 0
    total_missing_templates = 0

    tmpl_cache: Dict[Tuple[str, str], Dict[str, Any] | None] = {}
    templates_in_study_cache: Dict[str, int] = {}
    study_counts_today: Dict[str, int] = defaultdict(int)
    seq_counts_today: Dict[Tuple[str, str], int] = defaultdict(int)

    eligible_rows: List[sqlite3.Row] = []
    for row in acq_rows:
        if series_is_posthoc(row["SeriesNumber"]):
            continue
        project = row["Project"]
        seqname = row["SequenceName"]
        seqtype = row["SequenceType"]
        if not is_interesting_sequence_with_blacklist(project, seqname, seqtype):
            continue
        eligible_rows.append(row)
        study_counts_today[project] += 1
        seq_counts_today[(project, seqname)] += 1

    for row in eligible_rows:
        project = row["Project"]
        seqname = row["SequenceName"]
        key = (project, seqname)

        total_checked += 1
        seq_summary[key]["total"] += 1

        if key not in tmpl_cache:
            try:
                trow = db.get_template(project, seqname)
                tmpl_cache[key] = dict(trow) if trow else None
            except Exception:
                tmpl_cache[key] = None

        tmpl = tmpl_cache[key]
        if not tmpl:
            total_missing_templates += 1
            missing_templates[key]["count"] += 1

            if project not in templates_in_study_cache:
                templates_in_study_cache[project] = get_templates_in_study(sql, project)
            missing_templates[key]["templates_in_study"] = templates_in_study_cache[project]
            missing_templates[key]["study_count_today"] = int(study_counts_today.get(project, 0))
            missing_templates[key]["seq_count_today"] = int(seq_counts_today.get(key, 0))

            if not missing_templates[key].get("first_seen"):
                fs = first_seen_from_template_by_count(sql, project, seqname)
                if not fs:
                    fs = first_seen_date_for_seq(sql, project, seqname)
                missing_templates[key]["first_seen"] = fs

            if len(missing_templates[key]["examples"]) < 3:
                s3 = format_series_003(row["SeriesNumber"])
                missing_templates[key]["examples"].append(f"{project} / {row['SubID']} / {seqname}.{s3}")
            continue

        errors, marquee_mismatch = compare_row_against_template(row, tmpl, consts, MARQUEE_COLS)

        if errors:
            seq_summary[key]["anydiff"] += 1
            total_anydiff += 1
            for col in errors.keys():
                exp = tmpl.get(col)
                got = row[col] if col in row.keys() else None
                seq_summary[key]["mismatch_counts"][(col, str(exp), str(got))] += 1

        if marquee_mismatch:
            seq_summary[key]["nonconforming"] += 1
            total_nonconforming += 1
            if len(seq_summary[key]["examples"]) < 3:
                s3 = format_series_003(row["SeriesNumber"])
                diff_list = compact_diff_list(errors, MARQUEE_COLS, max_items=6)
                seq_summary[key]["examples"].append(
                    f"{project} / {row['SubID']} / {seqname}.{s3} (diffs: {diff_list})"
                )

    mia_actionable = 0
    for k in missing_templates.keys():
        if int(missing_templates[k].get("templates_in_study", 0)) > 0:
            mia_actionable += 1

    status_emoji = "✅" if (total_nonconforming == 0 and mia_actionable == 0) else "❌"
    subject = f"[MRQA] {status_emoji} {total_nonconforming}/{total_checked} ({total_seen_today}); {mia_actionable} MIA"

    lines: List[str] = []
    lines.append(f"MRQART header compliance summary for {date_label}")
    lines.append("")

    if total_nonconforming > 0:
        lines.append("❌ Non-Conforming:")
        lines.append("")
        for (project, seqname) in sorted(seq_summary.keys()):
            info = seq_summary[(project, seqname)]
            if info["nonconforming"] == 0:
                continue
            lines.append(f"* {project}/{seqname} ({info['nonconforming']}/{info['total']})")

            top_all = sorted(info["mismatch_counts"].items(), key=lambda kv: kv[1], reverse=True)
            shown = 0
            for ((col, exp, got), n) in top_all:
                if col not in set(MARQUEE_COLS) and col != "TA":
                    continue
                lines.append(f"   {format_expected_got(col, exp, got)} ({n})")
                shown += 1
                if shown >= 8:
                    break

            for ex in info["examples"]:
                lines.append(f"   - ex: {ex}")
            lines.append("")
    else:
        lines.append("✅ Non-Conforming:")
        lines.append("  none")
        lines.append("")

    if total_missing_templates > 0:
        mia_with_templates: List[Tuple[Tuple[str, str], Dict[str, Any]]] = []
        mia_no_study_templates: List[Tuple[Tuple[str, str], Dict[str, Any]]] = []

        for key in sorted(missing_templates.keys()):
            info = missing_templates[key]
            if int(info.get("templates_in_study", 0)) > 0:
                mia_with_templates.append((key, info))
            else:
                mia_no_study_templates.append((key, info))

        if mia_with_templates:
            lines.append("🕳️ MIA (study has templates) (study count, seq count, first seen; templates in study):")
            lines.append("")
            for (project, seqname), info in mia_with_templates:
                first_seen = info.get("first_seen") or "unknown"
                study_ct = info.get("study_count_today", 0)
                seq_ct = info.get("seq_count_today", 0)
                tmpl_ct = info.get("templates_in_study", 0)
                lines.append(f"  * {project}/{seqname} ({study_ct}, {seq_ct}, {first_seen}; {tmpl_ct})")
                for ex in info["examples"]:
                    lines.append(f"     - {ex}")
            lines.append("")

        if mia_no_study_templates:
            lines.append("🧱 No templates for study (not onboarded) (study count, seq count, first seen):")
            lines.append("")
            for (project, seqname), info in mia_no_study_templates:
                first_seen = info.get("first_seen") or "unknown"
                study_ct = info.get("study_count_today", 0)
                seq_ct = info.get("seq_count_today", 0)
                lines.append(f"  * {project}/{seqname} ({study_ct}, {seq_ct}, {first_seen})")
                for ex in info["examples"]:
                    lines.append(f"     - {ex}")
            lines.append("")
    else:
        lines.append("✅ MIA:")
        lines.append("  none")
        lines.append("")

    lines.append("ℹ️ Summary:")
    lines.append(f"  {total_seen_today} acquisitions were seen.")
    lines.append(f"  {total_checked} matched inspection criteria (interesting + series<=200).")
    lines.append(f"  {total_nonconforming} of those are nonconforming by marquee cols ({', '.join(MARQUEE_COLS)}).")
    lines.append(f"  {total_anydiff} of those differ from template for any reason (across CONSTS).")
    lines.append(f"  {total_missing_templates} do not have a template.")
    lines.append("")
    lines.append("— MRQART")

    body = "\n".join(lines)

    any_fail = False
    for e in email_entries:
        ok = send_via_local_mail(subject, body, e["to"])
        if ok:
            print(f"[ok] mailed {e['to']}")
        else:
            any_fail = True

    log_line(
        f"run date={date_label} seen={total_seen_today} checked={total_checked} "
        f"nonconf={total_nonconforming} anydiff={total_anydiff} "
        f"missing={total_missing_templates} mia={mia_actionable} subject={subject!r}"
    )
    dbg(
        f"done date={date_label} seen={total_seen_today} checked={total_checked} "
        f"nonconf={total_nonconforming} anydiff={total_anydiff} missing={total_missing_templates} mia={mia_actionable}"
    )

    return 0 if not any_fail else 7


if __name__ == "__main__":
    raise SystemExit(main())

