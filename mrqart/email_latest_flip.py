#!/usr/bin/env python3
"""
Daily header-compliance summary email based on db.sqlite.

Refactor note:
- main() is now a thin orchestration layer.
- Core logic is split into testable helpers:
  - get_report_date()
  - fetch_acquisitions()
  - select_eligible_rows()
  - _evaluate_row()         <-- per-row logic, extracted for testability
  - evaluate_rows()
  - format_seq_result()     <-- renders a single SeqSummary entry to lines
  - build_email()
  - send_all()

Behavior should be identical to the previous version.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

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


# -----------------------------
# Logging / debug
# -----------------------------
def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _debug_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = env or os.environ
    return env.get("MRQART_DEBUG", "").strip() not in ("", "0", "false", "False")


def _log_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = env or os.environ
    return env.get("MRQART_LOG", "").strip() not in ("", "0", "false", "False")


def _log_path(env: Mapping[str, str] | None = None) -> Path:
    env = env or os.environ
    p = env.get("MRQART_LOG_PATH", "").strip()
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


# -----------------------------
# Config loading
# -----------------------------
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
    # 20260306WF - externally set DRYRUN=1 to see message without emailing
    #              alternative to changing config
    if os.environ.get("DRYRUN"):
        print(f"DRYRUN - not sending {recipient} mail '{subject}'\n{body}")
        return True
    try:
        # check=True raises on non-zero exit, so if we reach the return we succeeded.
        subprocess.run(
            ["mail", "-s", subject, recipient],
            input=body.encode("utf-8"),
            check=True,
        )
        return True
    except Exception as e:
        print(f"[warn] local mail send failed to {recipient}: {e}", file=sys.stderr)
        return False


FilterSettings = Dict[str, Any]


def load_reporting_config(toml_path: Path) -> FilterSettings:
    """
    Load reporting settings from config/reporting.toml.

    Expected structure:
      [filter]
      interesting_substrings = [...]
      deny_substrings = [...]
      blacklist_seqtype_prefixes = [...]
      disable_blacklist = bool
      blacklist_study_regex = ["^Body", "^7TB"]

      [compare]
      marquee_cols = [...]

    Note: SequenceType is always added to marquee_set at evaluation time
    (in evaluate_rows) regardless of what is listed here.
    BWP and PixelResol are not forced but should be added to reporting.toml
    if you want them to get their own detail lines in the email.
    """
    if not toml_path.exists():
        raise FileNotFoundError(f"Missing reporting TOML: {toml_path}")

    cfg = toml.load(toml_path.open("rb"))

    filt = cfg.get("filter", {}) or {}
    comp = cfg.get("compare", {}) or {}

    default_filter = {
        "interesting_substrings": [],
        "deny_substrings": [],
        "blacklist_seqtype_prefixes": [],
        "blacklist_study_regex": [],
        "disable_blacklist": False,
        "marquee_cols": [
            "PED_major",
            "iPAT",
            "TR",
            "TE",
            "TA",
            "Matrix",
            "FA",
            "FoV",
            "BWP",
            "PixelResol",
        ],
    }

    settings = dict()
    # populate from 'filter' section. use defaults if missing or blank
    for k, v in default_filter.items():
        settings[k] = filt.get(k, v) or v

    # marquee comes from 'compare' which also includes fault tolerance settings
    settings["marquee_cols"] = list(
        comp.get("marquee_cols", default_filter["marquee_cols"])
    )

    return settings


# -----------------------------
# Formatting helpers
# -----------------------------
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


def compact_error_keys(
    errors: Dict[str, Any], prefer_cols: List[str], max_items: int = 6
) -> str:
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
    seqname: str, seqtype: str | None, settings: FilterSettings
) -> bool:
    """
    Rules:
      1) If SequenceName contains any interesting substring, include.
      2) Else if disable_blacklist is True, include.
      3) Else if SequenceType prefix is in blacklist, exclude.
      4) Else include.
    """

    interesting_substrings = settings.get("interesting_substrings")
    deny_substrings = settings.get("deny_substrings")
    blacklist_seqtype_prefixes = settings.get("blacklist_seqtype_prefixes")
    disable_blacklist = settings.get("disable_blacklist")

    sname = (seqname or "").lower()

    if deny_substrings and any(d.lower() in sname for d in deny_substrings):
        return False

    if interesting_substrings and any(
        sub.lower() in sname for sub in interesting_substrings
    ):
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


# -----------------------------
# Template metadata helpers
# -----------------------------
def yyyymmdd_to_iso(s: Any) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    if len(t) == 8 and t.isdigit():
        return f"{t[0:4]}-{t[4:6]}-{t[6:8]}"
    return t or None


def first_seen_from_template_by_count(
    sql: sqlite3.Connection, project: str, seqname: str
) -> str | None:
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


def first_seen_date_for_seq(
    sql: sqlite3.Connection, project: str, seqname: str
) -> str | None:
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


def get_physicist_for_project(sql: sqlite3.Connection, project: str) -> Optional[str]:
    """
    Look up the assigned physicist for a project by matching the suffix
    after '^' in the acq_param Project name against the project table.
    Case-insensitive. Returns None if no match or no physicist assigned.
    """
    row = sql.execute(
        """
        SELECT Physicist
        FROM project
        WHERE UPPER(Project) = UPPER(SUBSTR(?, INSTR(?, '^') + 1))
        LIMIT 1
        """,
        (project, project),
    ).fetchone()
    if not row or not row[0] or not str(row[0]).strip():
        return None
    return str(row[0]).strip()


@dataclass(frozen=True)
class ReportDate:
    report_date: datetime
    yday_str: str  # YYYYMMDD
    date_label: str  # YYYY-MM-DD


@dataclass
class Totals:
    total_seen_today: int = 0
    total_checked: int = 0
    total_nonconforming: int = 0
    total_anydiff: int = 0
    total_missing_templates: int = 0
    mia_actionable: int = 0


@dataclass
class RowResult:
    """Result of evaluating a single acquisition row against its template."""

    key: SeqKey
    missing_template: bool = False
    has_any_diff: bool = False
    has_marquee_mismatch: bool = False
    errors_dict: Dict[str, Dict[str, str]] = field(default_factory=dict)
    first_seen: Optional[str] = None
    study_has_templates: bool = False


@dataclass
class SeqSummary:
    """
    Aggregated conformance data for a single (project, subid, seqname) key.
    This is the canonical data structure for a single sequence check —
    populated by evaluate_rows and rendered by format_seq_result.
    """

    key: SeqKey
    total: int = 0
    nonconforming: int = 0
    anydiff: int = 0
    examples: List[str] = field(default_factory=list)
    mismatch_counts: Dict[Tuple[str, str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )

    @property
    def project(self) -> str:
        return self.key[0]

    @property
    def subid(self) -> str:
        return self.key[1]

    @property
    def seqname(self) -> str:
        return self.key[2]


def format_seq_result(
    summary: SeqSummary,
    *,
    marquee_cols: List[str],
) -> List[str]:
    """
    Render a single SeqSummary to a list of lines for inclusion in the email.
    Each nonconforming acquisition is a flat bullet: subid/seqname.acqnum
    with diffs indented below. No fraction or ex: line — the bullet IS the example.
    Bullets with no displayable diffs (e.g. only SequenceType) are silently skipped.
    Can be called independently for testing or iteration.
    """
    lines: List[str] = []

    for ex in summary.examples:
        # ex is stored as "project / subid / seqname.acqnum (diffs: ...)"
        # strip the project prefix and the trailing diffs annotation for the bullet
        # e.g. "Brain^CATOV-BRAIN / 118252 / Perfusion_Weighted.042 (diffs: TE, TA)"
        # becomes "118252/Perfusion_Weighted.042"
        ex_clean = ex
        parts = ex.split(" / ", 2)
        if len(parts) == 3:
            subid_part = parts[1].strip()
            seq_part = parts[2].split(" (diffs:")[0].strip()
            ex_clean = f"{subid_part}/{seq_part}"

        top_all = sorted(
            summary.mismatch_counts.items(), key=lambda kv: kv[1], reverse=True
        )
        diff_lines: List[str] = []
        shown = 0
        for (col, exp, got), n in top_all:
            if col not in set(marquee_cols):
                continue
            diff_lines.append(f"      {format_expected_got(col, exp, got)}")
            shown += 1
            if shown >= 8:
                break

        if diff_lines:
            lines.append(f"  * {ex_clean}")
            lines.extend(diff_lines)

    return lines


def get_report_date(env: Mapping[str, str], now: datetime | None = None) -> ReportDate:
    """
    Determine reporting date:
      - MRQART_DATE override supports YYYYMMDD or YYYY-MM-DD
      - default: yesterday relative to now
    """
    now = now or datetime.now()
    override = env.get("MRQART_DATE")
    if override:
        override = override.strip()
        yday_str = override.replace("-", "") if "-" in override else override
        report_date = datetime.strptime(yday_str, "%Y%m%d")
    else:
        report_date = now - timedelta(days=1)
        yday_str = report_date.strftime("%Y%m%d")

    return ReportDate(
        report_date=report_date,
        yday_str=yday_str,
        date_label=report_date.strftime("%Y-%m-%d"),
    )


def fetch_acquisitions(sql: sqlite3.Connection, yday_str: str) -> List[sqlite3.Row]:
    return sql.execute(
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


def select_eligible_rows(
    acq_rows: Iterable[sqlite3.Row], settings: FilterSettings
) -> Tuple[List[sqlite3.Row], Dict[str, int], Dict[SeqKey, int], Dict[str, set]]:
    """
    @param acq_rows  sql query results - acquisitions to check
    @param settings  configuration from load_reporting_config
                     passed to is_interesting_sequence_with_blacklist
    Apply:
      - SeriesNumber <= 200
      - reporting filter (interesting/deny/blacklist)
    Returns:
      - eligible rows
      - study_counts_today: total eligible rows per project
      - seq_counts_today: total eligible rows per (project, subid, seqname)
      - study_subids_today: set of unique SubIDs seen per project (for session count)
    """
    eligible: List[sqlite3.Row] = []
    study_counts_today: Dict[str, int] = defaultdict(int)
    seq_counts_today: Dict[SeqKey, int] = defaultdict(int)
    study_subids_today: Dict[str, set] = defaultdict(set)

    for row in acq_rows:
        if series_is_posthoc(row["SeriesNumber"]):
            continue

        project = row["Project"]
        subid = row["SubID"]
        seqname = row["SequenceName"]
        seqtype = row["SequenceType"]

        # skip blacklisted projects by regular expression
        skip = False
        for ignore_study_regex in settings.get("blacklist_study_regex", []):
            if re.search(ignore_study_regex, project):
                skip = True
                break
        if skip:
            continue

        if not is_interesting_sequence_with_blacklist(seqname, seqtype, settings):
            continue

        eligible.append(row)
        key: SeqKey = (project, subid, seqname)
        study_counts_today[project] += 1
        seq_counts_today[key] += 1
        study_subids_today[project].add(subid)

    return eligible, study_counts_today, seq_counts_today, study_subids_today


def _evaluate_row(
    row: sqlite3.Row,
    *,
    tc: TemplateChecker,
    marquee_set: set,
    sql: sqlite3.Connection,
    study_has_templates_fn: Callable[[sqlite3.Connection, str], bool],
    first_seen_from_templates_fn: Callable[[sqlite3.Connection, str, str], str | None],
    first_seen_from_acq_fn: Callable[[sqlite3.Connection, str, str], str | None],
    templates_in_study_cache: Dict[str, bool],
) -> RowResult:
    """
    Evaluate a single acquisition row against its template.
    Returns a RowResult describing what was found.
    RowResult wraps what TemplateChecker returns — no logic is duplicated,
    just structured for aggregation.
    """
    project = row["Project"]
    subid = row["SubID"]
    seqname = row["SequenceName"]
    key: SeqKey = (project, subid, seqname)

    hdr = dict(row)
    res = tc.check_header(hdr)

    # Missing template
    if not res.get("template"):
        if project not in templates_in_study_cache:
            templates_in_study_cache[project] = bool(
                study_has_templates_fn(sql, project)
            )
        study_has_tmpl = bool(templates_in_study_cache[project])

        fs = first_seen_from_templates_fn(sql, project, seqname)
        if not fs:
            fs = first_seen_from_acq_fn(sql, project, seqname)

        return RowResult(
            key=key,
            missing_template=True,
            study_has_templates=study_has_tmpl,
            first_seen=fs,
        )

    errors_dict: Dict[str, Dict[str, str]] = res.get("errors") or {}
    has_any_diff = bool(errors_dict)
    has_marquee_mismatch = any(col in marquee_set for col in errors_dict)

    return RowResult(
        key=key,
        missing_template=False,
        has_any_diff=has_any_diff,
        has_marquee_mismatch=has_marquee_mismatch,
        errors_dict=errors_dict,
    )


def evaluate_rows(
    eligible_rows: Iterable[sqlite3.Row],
    *,
    sql: sqlite3.Connection,
    tc: TemplateChecker,
    marquee_cols: List[str],
    study_counts_today: Mapping[str, int],
    seq_counts_today: Mapping[SeqKey, int],
    study_has_templates_fn: Callable[
        [sqlite3.Connection, str], bool
    ] = study_has_any_templates,
    first_seen_from_templates_fn: Callable[
        [sqlite3.Connection, str, str], str | None
    ] = first_seen_from_template_by_count,
    first_seen_from_acq_fn: Callable[
        [sqlite3.Connection, str, str], str | None
    ] = first_seen_date_for_seq,
) -> Tuple[Dict[SeqKey, SeqSummary], Dict[SeqKey, Dict[str, Any]], Totals]:
    """
    Core evaluation engine — calls _evaluate_row for each eligible row
    and aggregates results into seq_summary, missing_templates, and totals.

    SequenceType is always added to marquee_set here regardless of what is
    in reporting.toml, so SequenceType changes are always caught as nonconforming.
    """
    seq_summary: Dict[SeqKey, SeqSummary] = {}

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

    totals = Totals()

    # SequenceType is always included in marquee_set regardless of reporting.toml
    # so that a sequence type change without a name change is never silently ignored.
    marquee_set = set(marquee_cols) | {"SequenceType"}

    templates_in_study_cache: Dict[str, bool] = {}

    for row in eligible_rows:
        project = row["Project"]
        subid = row["SubID"]
        seqname = row["SequenceName"]
        key: SeqKey = (project, subid, seqname)

        totals.total_checked += 1

        if key not in seq_summary:
            seq_summary[key] = SeqSummary(key=key)
        seq_summary[key].total += 1

        result = _evaluate_row(
            row,
            tc=tc,
            marquee_set=marquee_set,
            sql=sql,
            study_has_templates_fn=study_has_templates_fn,
            first_seen_from_templates_fn=first_seen_from_templates_fn,
            first_seen_from_acq_fn=first_seen_from_acq_fn,
            templates_in_study_cache=templates_in_study_cache,
        )

        if result.missing_template:
            totals.total_missing_templates += 1
            missing_templates[key]["count"] += 1
            missing_templates[key]["study_has_templates"] = result.study_has_templates
            missing_templates[key]["study_count_today"] = int(
                study_counts_today.get(project, 0)
            )
            missing_templates[key]["seq_count_today"] = int(
                seq_counts_today.get(key, 0)
            )
            if not missing_templates[key].get("first_seen"):
                missing_templates[key]["first_seen"] = result.first_seen
            if len(missing_templates[key]["examples"]) < 3:
                s3 = format_series_003(row["SeriesNumber"])
                missing_templates[key]["examples"].append(
                    f"{project} / {subid} / {seqname}.{s3}"
                )
            continue

        if result.has_any_diff:
            seq_summary[key].anydiff += 1
            totals.total_anydiff += 1
            for col, cmp in result.errors_dict.items():
                exp = cmp.get("expect")
                got = cmp.get("have")
                seq_summary[key].mismatch_counts[(col, str(exp), str(got))] += 1

        if result.has_marquee_mismatch:
            seq_summary[key].nonconforming += 1
            totals.total_nonconforming += 1
            if len(seq_summary[key].examples) < 3:
                s3 = format_series_003(row["SeriesNumber"])
                diff_list = compact_error_keys(
                    result.errors_dict, marquee_cols, max_items=6
                )
                seq_summary[key].examples.append(
                    f"{project} / {subid} / {seqname}.{s3} (diffs: {diff_list})"
                )

    # actionable MIA = missing template keys where study is onboarded (has any templates)
    totals.mia_actionable = sum(
        1 for info in missing_templates.values() if info.get("study_has_templates")
    )

    return seq_summary, missing_templates, totals


def build_email(
    *,
    date_label: str,
    marquee_cols: List[str],
    total_seen_today: int,
    seq_summary: Dict[SeqKey, SeqSummary],
    missing_templates: Dict[SeqKey, Dict[str, Any]],
    totals: Totals,
    study_subids_today: Mapping[str, set],
    physicist_by_project: Mapping[str, Optional[str]],
) -> Tuple[str, str]:
    """
    Render subject + body from aggregated results.
    Nonconforming sequences are grouped by project; each acquisition is a
    flat bullet with diffs below. Project header shows session count today.
    """
    status_emoji = (
        "✅"
        if (totals.total_nonconforming == 0 and totals.mia_actionable == 0)
        else "❌"
    )
    subject = (
        f"[MRQA] {status_emoji} {totals.total_nonconforming}/{totals.total_checked} "
        f"({total_seen_today}); {totals.mia_actionable} MIA"
    )

    lines: List[str] = []
    lines.append(f"MRQART header compliance summary for {date_label}")
    lines.append("")

    # ---- Nonconforming section
    if totals.total_nonconforming > 0:
        lines.append("❌ Non-Conforming:")
        lines.append("")

        # Group nonconforming sequences by project
        by_project: Dict[str, List[SeqKey]] = defaultdict(list)
        for key in sorted(seq_summary.keys()):
            if seq_summary[key].nonconforming > 0:
                by_project[key[0]].append(key)

        for project in sorted(by_project.keys()):
            keys = by_project[project]
            project_lines: List[str] = []
            for key in keys:
                summary = seq_summary[key]
                project_lines.extend(
                    format_seq_result(summary, marquee_cols=marquee_cols)
                )

            if not project_lines:
                continue

            n_seq = len([l for l in project_lines if l.startswith("  *")])
            n_sessions = len(study_subids_today.get(project, set()))
            session_word = "session" if n_sessions == 1 else "sessions"
            seq_word = "sequence" if n_seq == 1 else "sequences"
            physicist = physicist_by_project.get(project)
            physicist_str = f"; physicist: {physicist}" if physicist else ""
            lines.append(
                f"{project} ({n_seq} nonconforming {seq_word}; {n_sessions} {session_word} today{physicist_str}):"
            )
            lines.extend(project_lines)
            lines.append("")
    else:
        lines.append("✅ Non-Conforming:")
        lines.append("  none")
        lines.append("")

    # ---- Missing templates section
    if totals.total_missing_templates > 0:
        mia_with_templates: List[Tuple[SeqKey, Dict[str, Any]]] = []
        mia_no_study_templates: List[Tuple[SeqKey, Dict[str, Any]]] = []

        for key in sorted(missing_templates.keys()):
            info = missing_templates[key]
            if info.get("study_has_templates"):
                mia_with_templates.append((key, info))
            else:
                mia_no_study_templates.append((key, info))

        if mia_with_templates:
            lines.append(
                "🕳️ MIA (study has templates) (study count, subj/seq count, first seen):"
            )
            lines.append("")
            for (project, subid, seqname), info in mia_with_templates:
                first_seen = info.get("first_seen") or "unknown"
                study_ct = info.get("study_count_today", 0)
                seq_ct = info.get("seq_count_today", 0)
                lines.append(
                    f"  * {project}/{subid}/{seqname} ({study_ct}, {seq_ct}, {first_seen})"
                )
                for ex in info["examples"]:
                    lines.append(f"     - {ex}")
            lines.append("")

        if mia_no_study_templates:
            lines.append(
                "🧱 No templates for study (not onboarded) (study count, subj/seq count, first seen):"
            )
            lines.append("")
            for (project, subid, seqname), info in mia_no_study_templates:
                first_seen = info.get("first_seen") or "unknown"
                study_ct = info.get("study_count_today", 0)
                seq_ct = info.get("seq_count_today", 0)
                lines.append(
                    f"  * {project}/{subid}/{seqname} ({study_ct}, {seq_ct}, {first_seen})"
                )
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
    lines.append(
        f"  {totals.total_checked} matched inspection criteria (interesting + series<=200)."
    )
    lines.append(
        f"  {totals.total_nonconforming} of those are nonconforming by marquee cols ({', '.join(marquee_cols)})."
    )
    lines.append(
        "  Note: comparisons are performed by TemplateChecker (strict per its implementation)."
    )
    lines.append(
        f"  {totals.total_anydiff} of those differ from template on at least one column (marquee or otherwise)."
    )
    lines.append(f"  {totals.total_missing_templates} do not have a template.")
    lines.append("")
    lines.append("— MRQART")

    body = "\n".join(lines)
    return subject, body

def build_jsonl_entries(
    *,
    date_label: str,
    seq_summary: Dict[SeqKey, SeqSummary],
    missing_templates: Dict[SeqKey, Dict[str, Any]],
    marquee_cols: List[str],
    physicist_by_project: Mapping[str, Optional[str]] = {},
) -> List[Dict[str, Any]]:
    """
    Build a list of JSONL entries for the web dashboard.
    One entry per nonconforming sequence or missing template.
    Conforming sequences are skipped to keep the log lean.
    """
    script_ts = _now_iso()
    entries: List[Dict[str, Any]] = []

    for key, summary in seq_summary.items():
        if summary.nonconforming == 0:
            continue
        project, subid, seqname = key
        top_errors = sorted(
            summary.mismatch_counts.items(), key=lambda kv: kv[1], reverse=True
        )
        errors = [
            format_expected_got(col, exp, got)
            for (col, exp, got), _ in top_errors
            if col in set(marquee_cols)
        ]
        if not errors:
            continue  # SequenceType-only mismatch - not displayable, skip
        entries.append(
            {
                "script_ts": script_ts,
                "project": project,
                "sequence": seqname,
                "subid": subid,
                "series": (
                    summary.examples[0].split(".")[-1].split(" ")[0]
                    if summary.examples
                    else ""
                ),
                "station": "",
                "acq_ts": date_label,
                "acq_ts_sort": date_label,
                "conforms": False,
                "error_count": len(errors),
                "errors": errors,
                "status": "NONCONFORM",
                "physicist": physicist_by_project.get(project) or "",
            }
        )

    for (project, subid, seqname), info in missing_templates.items():
        if not info.get("study_has_templates"):
            continue
        entries.append(
            {
                "script_ts": script_ts,
                "project": project,
                "sequence": seqname,
                "subid": subid,
                "series": "",
                "station": "",
                "acq_ts": date_label,
                "acq_ts_sort": date_label,
                "conforms": False,
                "error_count": 0,
                "errors": ["missing template"],
                "status": "NO_TEMPLATE",
                "physicist": physicist_by_project.get(project) or "",
            }
        )

    return entries


def send_all(
    email_entries: Iterable[Mapping[str, str]],
    subject: str,
    body: str,
    *,
    send_fn: Callable[[str, str, str], bool] = send_via_local_mail,
) -> bool:
    """
    Send the same subject/body to all recipients.
    Returns True if any failures occurred.
    """
    any_fail = False
    for e in email_entries:
        ok = send_fn(subject, body, e["to"])
        if ok:
            print(f"[ok] mailed {e['to']}")
        else:
            any_fail = True
    return any_fail


def main(*, dry_run: bool = False) -> int:
    env = os.environ

    # paths — all overridable via environment variables set by __main__.py
    db_path = Path(env.get("MRQART_DB", str(DEFAULT_DB)))
    reporting_path = Path(env.get("MRQART_REPORTING_TOML", str(REPORTING_TOML)))
    email_toml_path = Path(env.get("MRQART_EMAIL_TOML", str(EMAIL_TOML)))

    # db connect
    sql = sqlite3.connect(str(db_path))
    sql.row_factory = sqlite3.Row

    # templates. modifies DB. use SKIP_REBUILD to avoid
    if not os.environ.get("SKIP_REBUILD"):
        rebuild_templates(sql)

    # configs
    try:
        settings = load_reporting_config(reporting_path)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    if not settings.get("marquee_cols"):
        print("[error] reporting.toml: compare.marquee_cols is empty", file=sys.stderr)
        return 2

    if not dry_run:
        try:
            email_entries = load_email_entries(email_toml_path)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 2
        if not email_entries:
            print(f"[error] No usable recipients in {email_toml_path}", file=sys.stderr)
            return 2
    else:
        email_entries = []

    # date
    rd = get_report_date(env)

    # query
    acq_rows = fetch_acquisitions(sql, rd.yday_str)
    total_seen_today = len(acq_rows)

    # no data case
    if not acq_rows:
        subject = "[MRQA] ✅ 0/0 (0); 0 MIA"
        body = (
            f"MRQART header compliance summary for {rd.date_label}\n\n"
            "No acquisitions were found in the DB for this date.\n"
            "— MRQART\n"
        )
        if dry_run:
            print(f"Subject: {subject}\n")
            print(body)
            return 0
        any_fail = send_all(email_entries, subject, body)
        log_line(
            f"run date={rd.date_label} seen=0 checked=0 nonconf=0 mia=0 subject={subject!r}"
        )
        return 0 if not any_fail else 7

    # filter
    eligible_rows, study_counts_today, seq_counts_today, study_subids_today = (
        select_eligible_rows(acq_rows, settings)
    )

    # engine
    tc = TemplateChecker(db=sql, context="DB")
    seq_summary, missing_templates, totals = evaluate_rows(
        eligible_rows,
        sql=sql,
        tc=tc,
        marquee_cols=settings["marquee_cols"],
        study_counts_today=study_counts_today,
        seq_counts_today=seq_counts_today,
    )
    totals.total_seen_today = total_seen_today

    physicist_by_project = {
        key[0]: get_physicist_for_project(sql, key[0]) for key in seq_summary
    }

    # render
    subject, body = build_email(
        date_label=rd.date_label,
        marquee_cols=settings["marquee_cols"],
        total_seen_today=total_seen_today,
        seq_summary=seq_summary,
        missing_templates=missing_templates,
        totals=totals,
        study_subids_today=study_subids_today,
        physicist_by_project=physicist_by_project,
    )

    # web dashboard
    web_log = Path(env.get("MRQART_WEB_LOG", ""))
    web_html = Path(env.get("MRQART_WEB_HTML", ""))
    if web_log and web_log.name:
        from .web_report import append_entries, render_html

        entries = build_jsonl_entries(
            date_label=rd.date_label,
            seq_summary=seq_summary,
            missing_templates=missing_templates,
            marquee_cols=settings["marquee_cols"],
            physicist_by_project=physicist_by_project,
        )
        append_entries(entries, web_log)
        if web_html and web_html.name:
            render_html(
                web_log, web_html, title=env.get("MRQART_WEB_TITLE", "MRQART QA — Feed")
            )

    # dry run: print instead of send
    if dry_run:
        print(f"Subject: {subject}\n")
        print(body)
        log_line(
            f"dry-run date={rd.date_label} seen={total_seen_today} checked={totals.total_checked} "
            f"nonconf={totals.total_nonconforming} subject={subject!r}"
        )
        return 0

    # send
    any_fail = send_all(email_entries, subject, body)

    # log
    log_line(
        f"run date={rd.date_label} seen={total_seen_today} checked={totals.total_checked} "
        f"nonconf={totals.total_nonconforming} anydiff={totals.total_anydiff} "
        f"missing={totals.total_missing_templates} mia={totals.mia_actionable} subject={subject!r}"
    )
    dbg(
        f"done date={rd.date_label} seen={total_seen_today} checked={totals.total_checked} "
        f"nonconf={totals.total_nonconforming} anydiff={totals.total_anydiff} "
        f"missing={totals.total_missing_templates} mia={totals.mia_actionable}"
    )

    sql.close()
    return 0 if not any_fail else 7


if __name__ == "__main__":
    raise SystemExit(main())
