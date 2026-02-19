#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def _as_float(x: Any) -> float | None:
    try:
        return float(x)
    except Exception:
        return None


def _norm(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() in ("", "null", "none"):
        return ""
    return s


def _sorted_values_seen(values: Iterable[Any]) -> List[str]:
    """
    Sort values numerically where possible, otherwise lexicographically.
    Keeps original string forms (so 'TA 46.86' stays that way).
    """
    raw = {_norm(v) for v in values}
    raw.discard("")
    floats: List[Tuple[float, str]] = []
    strings: List[str] = []

    for s in raw:
        fv = _as_float(s)
        if fv is not None:
            floats.append((fv, s))
        else:
            strings.append(s)

    floats_sorted = [s for _, s in sorted(floats, key=lambda t: t[0])]
    strings_sorted = sorted(strings)
    return floats_sorted + strings_sorted


@dataclass(frozen=True)
class SeqMismatch:
    col: str
    expect: str
    n_mismatch: int
    n_total: int
    values_seen: List[str]
    series_examples: List[str]


def _fetch_rows(
    sql: sqlite3.Connection,
    *,
    project: str,
    subid: str,
    seqname: str,
    max_series: int,
) -> List[sqlite3.Row]:
    return sql.execute(
        """
        SELECT a.AcqDate, a.AcqTime, a.Station, a.SubID, a.SeriesNumber,
               p.Project, p.SequenceName, p.SequenceType,
               p.TR, p.TE, p.FA, p.TA, p.FoV, p.Matrix, p.PixelResol, p.BWP, p.BWPPE,
               p.Phase, p.PED_major, p.Comments
        FROM acq a
        JOIN acq_param p ON a.param_id = p.rowid
        WHERE p.Project = ?
          AND a.SubID = ?
          AND p.SequenceName = ?
          AND CAST(a.SeriesNumber AS INT) <= ?
        ORDER BY a.AcqDate, a.AcqTime, CAST(a.SeriesNumber AS INT)
        """,
        (project, subid, seqname, int(max_series)),
    ).fetchall()


def _fetch_template(sql: sqlite3.Connection, *, project: str, seqname: str) -> sqlite3.Row | None:
    return sql.execute(
        """
        SELECT tp.*
        FROM template_by_count t
        JOIN acq_param tp ON tp.rowid = t.param_id
        WHERE t.Project = ?
          AND t.SequenceName = ?
        LIMIT 1
        """,
        (project, seqname),
    ).fetchone()


def _col_value(row: sqlite3.Row, col: str) -> Any:
    try:
        return row[col]
    except Exception:
        return None


def _series_int(x: Any) -> int | None:
    try:
        return int(str(x).strip())
    except Exception:
        return None


def _series_str(x: Any) -> str:
    si = _series_int(x)
    if si is None:
        return str(x)
    return str(si)


def _summarize_mismatches(
    *,
    rows: List[sqlite3.Row],
    template: sqlite3.Row,
    marquee_cols: List[str],
) -> List[SeqMismatch]:
    mismatches: List[SeqMismatch] = []
    if not rows:
        return mismatches

    # For each marquee col, compare normalized values as strings.
    for col in marquee_cols:
        exp = _norm(_col_value(template, col))
        if exp == "":
            # If template doesn't have it, don't flag it here.
            continue

        have_vals = [_col_value(r, col) for r in rows]
        have_norm = [_norm(v) for v in have_vals]

        # mismatch indices where have != expect and have is not empty
        idx = [i for i, hv in enumerate(have_norm) if hv != "" and hv != exp]
        if not idx:
            continue

        values_seen = _sorted_values_seen(have_vals)
        series_examples: List[str] = []
        for i in idx:
            if len(series_examples) >= 6:
                break
            series_examples.append(_series_str(_col_value(rows[i], "SeriesNumber")))

        mismatches.append(
            SeqMismatch(
                col=col,
                expect=exp,
                n_mismatch=len(idx),
                n_total=len(rows),
                values_seen=values_seen,
                series_examples=series_examples,
            )
        )

    return mismatches


def render_seq_report(
    *,
    project: str,
    subid: str,
    seqname: str,
    db_path: Path,
    max_series: int = 200,
    marquee_cols: List[str] | None = None,
    examples: int = 0,
) -> str:
    marquee_cols = marquee_cols or ["TR", "TE", "FA", "TA", "FoV", "Matrix", "PixelResol", "BWP", "BWPPE", "SequenceType", "Comments"]

    sql = sqlite3.connect(str(db_path))
    sql.row_factory = sqlite3.Row

    rows = _fetch_rows(sql, project=project, subid=subid, seqname=seqname, max_series=max_series)

    out: List[str] = []
    out.append("MRQART per-sequence summary")
    out.append(f"  Project:  {project}")
    out.append(f"  Sequence: {seqname}")
    out.append(f"  SubID:    {subid}")
    out.append("")
    out.append(f"  Rows matched: {len(rows)}")

    if rows:
        dates = [str(_col_value(r, "AcqDate")) for r in rows if _norm(_col_value(r, "AcqDate")) != ""]
        series = [_series_int(_col_value(r, "SeriesNumber")) for r in rows]
        series = [s for s in series if s is not None]

        if dates:
            out.append(f"  Date range:   {min(dates)} .. {max(dates)}")
        if series:
            out.append(f"  Series range: {min(series)} .. {max(series)}")
    out.append("")

    tmpl = _fetch_template(sql, project=project, seqname=seqname)
    if tmpl is None:
        out.append("🕳️ No template found in template_by_count for this Project/SequenceName.")
        out.append("— seq-report")
        return "\n".join(out)

    # Print template fields (only those we care about)
    out.append("Template (from template_by_count):")
    for col in ["SequenceType", "TR", "TE", "FA", "TA", "FoV", "Matrix", "PixelResol", "BWP", "BWPPE", "Phase", "PED_major", "Comments"]:
        v = _col_value(tmpl, col)
        if _norm(v) != "":
            out.append(f"  {col}: {v}")
    out.append("")

    mism = _summarize_mismatches(rows=rows, template=tmpl, marquee_cols=marquee_cols)
    if mism:
        out.append("❌ Mismatches vs template (marquee cols):")
        for m in mism:
            seen_str = ", ".join(m.values_seen)
            out.append(
                f"* {m.col}: expected {m.expect}, saw {seen_str}  ({m.n_mismatch}/{m.n_total} rows mismatched)"
            )
            if m.series_examples:
                out.append(f"    series examples: {', '.join(m.series_examples)}")
        out.append("")
    else:
        out.append("✅ No mismatches vs template (marquee cols).")
        out.append("")

    if examples and examples > 0 and rows:
        out.append(f"Examples (first {examples} rows):")
        for r in rows[:examples]:
            out.append(
                f"  {r['AcqDate']} {r['AcqTime']}  SubID={r['SubID']}  Series={r['SeriesNumber']}  Station={r['Station']}"
            )
        out.append("")

    out.append("— seq-report")
    return "\n".join(out)

