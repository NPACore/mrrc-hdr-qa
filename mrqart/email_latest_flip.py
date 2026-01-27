#!/usr/bin/env python3
"""
Daily header-compliance summary email based on db.sqlite.

- Looks at acquisitions with AcqDate = yesterday (or MRQART_DATE override).
- Rebuilds template_by_count each run from make_template_by_count.sql.
- Uses TemplateChecker (template selection + CONSTS comparison).
- Groups by (Project, SubID, SequenceName).
- Skips SeriesNumber > 200; formats SeriesNumber as %03d.
- Reports non-conforming acquisitions (marquee cols) and missing templates split by onboarding state.
- Reporting behavior (filtering + marquee cols) is driven by config/reporting.toml.
  (TemplateChecker comparisons are currently strict, per its implementation.)
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

from .template_checker import TemplateChecker
try:
    import tomllib as toml  # Python 3.11+
except Exception:
    import toml  # type: ignore


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "db.sqlite"
EMAIL_TOML = BASE_DIR / "config" / "email_settings.toml"
REPORTING_TOML = BASE_DIR / "config" / "reporting.toml"
TEMPLATE_SQL = BASE_DIR / "make_template_by_count.sql"
DEFAULT_LOG_PATH = BASE_DIR / "logs" / "mrqart_daily.log"

# Key: (Project, SubID, SequenceName)
SeqKey = Tuple[str, str, str]


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


def load_reporting_config(toml_path: Path) -> Dict[str, Any]:
    """
    Load reporting settings from config/reporting.toml.

    Expected structure:
      [filter]
      interesting_substrings = [...]
      deny_substrings = [...]
      blacklist_seqtype_prefixes = [...]
      disable_blacklist = bool

      [compare]
      marquee_cols = [...]
    """
    if not toml_path.exists():
        raise FileNotFoundError(f"Missing reporting TOML: {toml_path}")

    cfg = toml.load(toml_path.open("rb"))

    filt = cfg.get("filter", {}) or {}
    comp = cfg.get("compare", {}) or {}

    interesting = list(filt.get("interesting_substrings", []) or [])
    deny = list(filt.get("deny_substrings", []) or [])
    blacklist = list(filt.get("blacklist_seqtype_prefixes", []) or [])
    disable_blacklist = bool(filt.get("disable_blacklist", False))

    marquee = list(comp.get("marquee_cols", []) or [])

    return {
        "interesting_substrings": interesting,
        "deny_substrings": deny,
        "blacklist_seqtype_prefixes": blacklist,
        "disable_blacklist": disable_blacklist,
        "marquee_cols": marquee,
    }


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


def _as_float(x: Any) -> float | None:
    try:
        return float(x)
    except Exception:
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


def compact_error_keys(errors: Dict[str, Any], prefer_cols: List[str], max_items: int = 6) -> str:
    """
    errors is dict keyed by col name. prefer marquee cols + TA first.
    """
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


def is_interesting_sequence_with_blacklist(
    seqname: str,
    seqtype: str | None,
    interesting_substrings: List[str],
    deny_substrings: List[str],
    blacklist_seqtype_prefixes: List[str],
    disable_blacklist: bool,
) -> bool:
    """
    Rules:
      1) If SequenceName contains any interesting substring, include.
      2) Else if disable_blacklist is True, include.
      3) Else if SequenceType prefix is in blacklist, exclude.
      4) Else include.
    """
    sname = (seqname or "").lower()

    if deny_substrings and any(d.lower() in sname for d in deny_substrings):
        return False

    if interesting_substrings and any(sub.lower() in sname for sub in interesting_substrings):
        return True

    if disable_blacklist:
        return True

    stype = (seqtype or "").lower()
    if stype and blacklist_seqtype_prefixes:
        prefix = stype.split("_", 1)[0]
        blk = {p.lower() for p in blacklist_seqtype_prefixes}
        if prefix in blk:
            return False

    return True


def yyyymmdd_to_iso(s: Any) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    if len(t) == 8 and t.isdigit():
        return f"{t[0:4]}-{t[4:6]}-{t[6:8]}"
    return t or None


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


def study_has_any_templates(sql: sqlite3.Connection, project: str) -> bool:
    row = sql.execute(
        "SELECT 1 FROM template_by_count WHERE Project = ? LIMIT 1",
        (project,),
    ).fetchone()
    return row is not None


def main() -> int:
    db_path = Path(os.environ.get("MRQART_DB", DEFAULT_DB))
    sql = sqlite3.connect(str(db_path))
    sql.row_factory = sqlite3.Row

    rebuild_templates(sql)

    # Reporting config path can be overridden
    reporting_path = Path(os.environ.get("MRQART_REPORTING_TOML", str(REPORTING_TOML)))
    try:
        rpt = load_reporting_config(reporting_path)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    deny_substrings: List[str] = rpt.get("deny_substrings", [])
    interesting_substrings: List[str] = rpt["interesting_substrings"]
    blacklist_prefixes: List[str] = rpt["blacklist_seqtype_prefixes"]
    disable_blacklist: bool = rpt["disable_blacklist"]
    marquee_cols: List[str] = rpt["marquee_cols"]

    if not marquee_cols:
        print("[error] reporting.toml: compare.marquee_cols is empty", file=sys.stderr)
        return 2

    try:
        email_entries = load_email_entries(EMAIL_TOML)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    if not email_entries:
        print(f"[error] No usable recipients in {EMAIL_TOML}", file=sys.stderr)
        return 2

    # Template selection + comparison engine
    tc = TemplateChecker(db=sql, context="DB")

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

    seq_summary: Dict[SeqKey, Dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "nonconforming": 0,
            "anydiff": 0,
            "examples": [],
            "mismatch_counts": defaultdict(int),
        }
    )

    missing_templates: Dict[SeqKey, Dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "examples": [],
            "first_seen": None,
            "study_has_templates": False,
            "study_count_today": 0,
            "seq_count_today": 0,
        }
    )

    total_checked = 0
    total_nonconforming = 0
    total_anydiff = 0
    total_missing_templates = 0

    templates_in_study_cache: Dict[str, bool] = {}
    study_counts_today: Dict[str, int] = defaultdict(int)
    seq_counts_today: Dict[SeqKey, int] = defaultdict(int)

    eligible_rows: List[sqlite3.Row] = []
    for row in acq_rows:
        if series_is_posthoc(row["SeriesNumber"]):
            continue

        project = row["Project"]
        subid = row["SubID"]
        seqname = row["SequenceName"]
        seqtype = row["SequenceType"]

        if not is_interesting_sequence_with_blacklist(
            seqname=seqname,
            seqtype=seqtype,
            interesting_substrings=interesting_substrings,
            deny_substrings=deny_substrings,
            blacklist_seqtype_prefixes=blacklist_prefixes,
            disable_blacklist=disable_blacklist,
        ):
            continue

        eligible_rows.append(row)
        key: SeqKey = (project, subid, seqname)
        study_counts_today[project] += 1
        seq_counts_today[key] += 1

    for row in eligible_rows:
        project = row["Project"]
        subid = row["SubID"]
        seqname = row["SequenceName"]
        key: SeqKey = (project, subid, seqname)

        total_checked += 1
        seq_summary[key]["total"] += 1

        hdr = dict(row)
        res = tc.check_header(hdr)

        # Missing template: TemplateChecker returns template={} when absent
        if not res["template"]:
            total_missing_templates += 1
            missing_templates[key]["count"] += 1

            if project not in templates_in_study_cache:
                templates_in_study_cache[project] = study_has_any_templates(sql, project)
            missing_templates[key]["study_has_templates"] = bool(templates_in_study_cache[project])
            missing_templates[key]["study_count_today"] = int(study_counts_today.get(project, 0))
            missing_templates[key]["seq_count_today"] = int(seq_counts_today.get(key, 0))

            if not missing_templates[key].get("first_seen"):
                fs = first_seen_from_template_by_count(sql, project, seqname)
                if not fs:
                    fs = first_seen_date_for_seq(sql, project, seqname)
                missing_templates[key]["first_seen"] = fs

            if len(missing_templates[key]["examples"]) < 3:
                s3 = format_series_003(row["SeriesNumber"])
                missing_templates[key]["examples"].append(f"{project} / {subid} / {seqname}.{s3}")
            continue

        errors_dict: Dict[str, Dict[str, str]] = res["errors"] or {}

        if errors_dict:
            seq_summary[key]["anydiff"] += 1
            total_anydiff += 1
            for col, cmp in errors_dict.items():
                exp = cmp.get("expect")
                got = cmp.get("have")
                seq_summary[key]["mismatch_counts"][(col, str(exp), str(got))] += 1

        marquee_set = set(marquee_cols)
        marquee_mismatch = any((col in marquee_set) for col in errors_dict.keys())

        if marquee_mismatch:
            seq_summary[key]["nonconforming"] += 1
            total_nonconforming += 1
            if len(seq_summary[key]["examples"]) < 3:
                s3 = format_series_003(row["SeriesNumber"])
                diff_list = compact_error_keys(errors_dict, marquee_cols, max_items=6)
                seq_summary[key]["examples"].append(
                    f"{project} / {subid} / {seqname}.{s3} (diffs: {diff_list})"
                )

    # actionable MIA = missing template keys where study is onboarded (has any templates)
    mia_actionable = 0
    for k, info in missing_templates.items():
        if info.get("study_has_templates"):
            mia_actionable += 1

    status_emoji = "✅" if (total_nonconforming == 0 and mia_actionable == 0) else "❌"
    subject = f"[MRQA] {status_emoji} {total_nonconforming}/{total_checked} ({total_seen_today}); {mia_actionable} MIA"

    lines: List[str] = []
    lines.append(f"MRQART header compliance summary for {date_label}")
    lines.append("")

    # ---- Nonconforming section
    if total_nonconforming > 0:
        lines.append("❌ Non-Conforming:")
        lines.append("")
        for (project, subid, seqname) in sorted(seq_summary.keys()):
            info = seq_summary[(project, subid, seqname)]
            if info["nonconforming"] == 0:
                continue

            lines.append(f"* {project}/{subid}/{seqname} ({info['nonconforming']}/{info['total']})")

            top_all = sorted(info["mismatch_counts"].items(), key=lambda kv: kv[1], reverse=True)
            shown = 0
            for ((col, exp, got), n) in top_all:
                # keep the email focused; include marquee cols + TA if present
                if col not in set(marquee_cols) and col != "TA":
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

    # ---- Missing templates section
    if total_missing_templates > 0:
        mia_with_templates: List[Tuple[SeqKey, Dict[str, Any]]] = []
        mia_no_study_templates: List[Tuple[SeqKey, Dict[str, Any]]] = []

        for key in sorted(missing_templates.keys()):
            info = missing_templates[key]
            if info.get("study_has_templates"):
                mia_with_templates.append((key, info))
            else:
                mia_no_study_templates.append((key, info))

        if mia_with_templates:
            lines.append("🕳️ MIA (study has templates) (study count, subj/seq count, first seen):")
            lines.append("")
            for (project, subid, seqname), info in mia_with_templates:
                first_seen = info.get("first_seen") or "unknown"
                study_ct = info.get("study_count_today", 0)
                seq_ct = info.get("seq_count_today", 0)
                lines.append(f"  * {project}/{subid}/{seqname} ({study_ct}, {seq_ct}, {first_seen})")
                for ex in info["examples"]:
                    lines.append(f"     - {ex}")
            lines.append("")

        if mia_no_study_templates:
            lines.append("🧱 No templates for study (not onboarded) (study count, subj/seq count, first seen):")
            lines.append("")
            for (project, subid, seqname), info in mia_no_study_templates:
                first_seen = info.get("first_seen") or "unknown"
                study_ct = info.get("study_count_today", 0)
                seq_ct = info.get("seq_count_today", 0)
                lines.append(f"  * {project}/{subid}/{seqname} ({study_ct}, {seq_ct}, {first_seen})")
                for ex in info["examples"]:
                    lines.append(f"     - {ex}")
            lines.append("")
    else:
        lines.append("✅ MIA:")
        lines.append("  none")
        lines.append("")

    # ---- Summary
    lines.append("ℹ️ Summary:")
    lines.append(f"  {total_seen_today} acquisitions were seen.")
    lines.append(f"  {total_checked} matched inspection criteria (interesting + series<=200).")
    lines.append(f"  {total_nonconforming} of those are nonconforming by marquee cols ({', '.join(marquee_cols)}).")
    lines.append("  Note: comparisons are performed by TemplateChecker (strict per its implementation).")
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
