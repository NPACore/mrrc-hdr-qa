#!/usr/bin/env python3
import os, re, sqlite3, subprocess, sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EMAIL_TOML = Path(__file__).resolve().parent.parent / "config" / "email_settings.toml"
DB_PATH = Path(__file__).resolve().parent.parent / "db.sqlite"
os.environ.setdefault("MRQART_DB", str(DB_PATH))

# Env toggles (same as before, plus 3 for web output)
# MRQART_SINCE, MRQART_PROJECT, MRQART_SEQNAME, MRQART_PER_PAIR_LIMIT
# MRQART_SPLIT_EMAILS, MRQART_NOTIFY_ON_NO_TEMPLATE, MRQART_SKIP_CASEONLY
# MRQART_FORCE_EMAIL, MRQART_LEGACY_FORMAT
# MRQART_WEB_LOG (default: static/mrqart_log.jsonl)
# MRQART_WEB_HTML (default: static/mrqart_report.html)
# MRQART_WEB_TITLE (default: "MRQART QA — Feed")

try:
    import tomllib as toml  # py311+
except Exception:
    import toml  # type: ignore

from mrqart.acq2sqlite import DBQuery
from mrqart.web_report import append_entries, render_html

# ------------- helpers -------------
def rowdict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}

def _as_float(x: Any):
    if x is None: return None
    try: return float(x)
    except Exception:
        s = re.sub(r"[^\d.\-eE]", "", str(x))
        try: return float(s) if s else None
        except Exception: return None

def _norm_str(x: Any) -> Optional[str]:
    if x is None: return None
    return re.sub(r"\s+", " ", str(x)).strip().casefold()

def load_email_entries(toml_path: Path) -> List[Dict[str, str]]:
    if not toml_path.exists():
        raise FileNotFoundError(f"Missing TOML: {toml_path}")
    cfg = toml.load(toml_path.open("rb"))
    out: List[Dict[str, str]] = []
    for e in cfg.get("emails", []):
        sender = e.get("from")
        tos = e.get("to", [])
        if isinstance(tos, str):
            tos = [t.strip() for t in tos.split(",") if t.strip()]
        if not sender or not tos:
            continue
        for addr in tos:
            out.append({"from": sender, "to": addr})
    return out

def send_via_local_mail(subject: str, body: str, recipient: str) -> bool:
    try:
        proc = subprocess.run(["mail", "-s", subject, recipient],
                              input=body.encode("utf-8"), check=True)
        return proc.returncode == 0
    except Exception as e:
        print(f"[warn] local mail send failed to {recipient}: {e}", file=sys.stderr)
        return False

def fetch_param_row(sql: sqlite3.Connection, param_id: int) -> Optional[Dict[str, Any]]:
    cur = sql.execute("select rowid, * from acq_param where rowid = ?", (param_id,))
    row = cur.fetchone()
    return rowdict(row) if row else None

def compare_params(acq_param: Dict[str, Any], tmpl_param: Dict[str, Any], skip_caseonly: bool=False) -> Dict[str, str]:
    from mrqart.acq2sqlite import DBQuery as _DBQ
    errors: Dict[str, str] = {}
    for key in _DBQ.CONSTS:
        got, exp = acq_param.get(key), tmpl_param.get(key)
        gv, ev = _as_float(got), _as_float(exp)
        if gv is not None and ev is not None:
            if abs(gv - ev) > 1e-6:
                errors[key] = f"expected {exp}, got {got}"
        else:
            gns, ens = _norm_str(got), _norm_str(exp)
            if gns != ens:
                if skip_caseonly and got is not None and exp is not None and gns == ens:
                    continue
                errors[key] = f"expected {exp}, got {got}"
    return errors

def format_one_failure(acq: Dict[str, Any], ap: Dict[str, Any], errors: Dict[str, str], db_used: str) -> str:
    proj = ap.get("Project", "N/A"); seq = ap.get("SequenceName", "N/A")
    fa = ap.get("FA", "N/A"); station = acq.get("Station", "N/A")
    series = acq.get("SeriesNumber", "N/A"); subid = acq.get("SubID", "N/A")
    acq_dt = f"{acq.get('AcqDate','????')} {acq.get('AcqTime','????')}"
    err_text = "\n".join(f"  - {k}: {v}" for k,v in errors.items()) or "  - None"
    return (
        f"Project: {proj}\nSequence: {seq}\nSubject: {subid}\nSeriesNumber: {series}\n"
        f"Station: {station}\nFlip Angle (DB acq_param): {fa}\nAcq Timestamp (DB): {acq_dt}\n"
        f"Errors ({len(errors)}):\n{err_text}\n(DB used: {db_used})\n———\n"
    )

def summarize_failures(fails: List[str], since_str: str) -> Tuple[str, str]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subj = f"MRQART: Non-conforming acquisitions since {since_str} — total={len(fails)}"
    body = (f"Header compliance check for acquisitions since {since_str}\n"
            f"Non-conforming count: {len(fails)}\n\n" + "\n".join(fails) +
            f"\nTimestamp: {now}\n— MRQART\n")
    return subj, body

# ------------- main -------------
def main() -> int:
    db_used = os.environ.get("MRQART_DB", str(DB_PATH))
    notify_no_tmpl = os.environ.get("MRQART_NOTIFY_ON_NO_TEMPLATE", "0") == "1"
    split_emails   = os.environ.get("MRQART_SPLIT_EMAILS", "0") == "1"
    skip_caseonly  = os.environ.get("MRQART_SKIP_CASEONLY", "0") == "1"
    project_like   = os.environ.get("MRQART_PROJECT", "%")
    seq_like       = os.environ.get("MRQART_SEQNAME", "%")
    since_arg      = os.environ.get("MRQART_SINCE")
    per_pair_limit = int(os.environ.get("MRQART_PER_PAIR_LIMIT", "0") or 0)
    force_email    = os.environ.get("MRQART_FORCE_EMAIL", "0") == "1"

    # Web report outputs
    default_static = Path(__file__).resolve().parent.parent / "static"
    web_log  = Path(os.environ.get("MRQART_WEB_LOG",  str(default_static / "mrqart_log.jsonl")))
    web_html = Path(os.environ.get("MRQART_WEB_HTML", str(default_static / "mrqart_report.html")))
    web_title = os.environ.get("MRQART_WEB_TITLE", "MRQART QA — Feed")

    def persist_report(entries: List[Dict[str, Any]]) -> None:
        try:
            append_entries(entries, web_log)
            render_html(web_log, web_html, title=web_title)
            print(f"[ok] updated report: {web_html}")
        except Exception as e:
            print(f"[warn] could not update web report: {e}", file=sys.stderr)

    try:
        email_entries = load_email_entries(EMAIL_TOML)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr); return 2
    if not email_entries:
        print(f"[error] No usable recipients in {EMAIL_TOML}", file=sys.stderr); return 2

    sql = sqlite3.connect(str(DB_PATH)); sql.row_factory = sqlite3.Row
    dbq = DBQuery(sql)

    # Query rows (use filtered/per-pair helpers you added to DBQuery)
    try:
        if per_pair_limit > 0:
            acqs_rows = dbq.find_recent_per_pair(since_arg, project_like, seq_like, per_pair_limit)
        else:
            acqs_rows = dbq.find_acquisitions_since_filtered(since_arg, project_like, seq_like)
    except Exception as e:
        print(f"[error] filtered query failed: {e}", file=sys.stderr); return 3

    results_for_web: List[Dict[str, Any]] = []

    if not acqs_rows:
        if not force_email:
            print("[info] No acquisitions found in the given window (after filters).")
            persist_report(results_for_web); return 0
        # forced summary (0 scanned)
        since_str = since_arg or "yesterday"
        subject = f"MRQART: Forced summary since {since_str} — 0 non-conforming (scanned=0)"
        body = (f"Header compliance check for acquisitions since {since_str}\n"
                f"Non-conforming count: 0\nScanned acquisitions in window: 0\n\n"
                f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n— MRQART\n")
        any_fail = False
        for e in email_entries:
            ok = send_via_local_mail(subject, body, e["to"])
            print(f"[{'ok' if ok else 'fail'}] mailed {e['to']}"); any_fail |= (not ok)
        persist_report(results_for_web); return 0 if not any_fail else 7

    failures: List[str] = []
    per_email_payloads: List[Tuple[str, str]] = []

    for acq_row in acqs_rows:
        acq = rowdict(acq_row)
        param_id = acq.get("param_id")
        if param_id is None: continue
        ap = fetch_param_row(sql, int(param_id))
        if not ap: continue

        proj = ap.get("Project") or ""
        seq  = ap.get("SequenceName") or ""
        tmpl_row = dbq.get_template(proj, seq)
        tmpl = rowdict(tmpl_row) if isinstance(tmpl_row, sqlite3.Row) else tmpl_row

        errors: Dict[str, str] = {}
        if tmpl: errors = compare_params(ap, tmpl, skip_caseonly=skip_caseonly)

        # build web entry (log everything)
        script_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        acq_ts = f"{acq.get('AcqDate','????')} {acq.get('AcqTime','????')}"
        results_for_web.append({
            "script_ts": script_ts,
            "project": proj, "sequence": seq,
            "subid": acq.get("SubID",""), "series": acq.get("SeriesNumber",""),
            "station": acq.get("Station",""),
            "acq_ts": acq_ts,
            "acq_ts_sort": f"{acq.get('AcqDate','')} {acq.get('AcqTime','')}",
            "conforms": None if not tmpl else (len(errors) == 0),
            "error_count": 0 if not tmpl else len(errors),
            "errors": [] if not tmpl else [f"{k}: {v}" for k,v in errors.items()],
            "status": "NO_TEMPLATE" if not tmpl else ("OK" if not errors else "NONCONFORM"),
        })

        # emails only for issues / missing template (optional)
        if not tmpl:
            if notify_no_tmpl:
                body = (
                    "Header compliance check (NO TEMPLATE FOUND)\n"
                    f"Project: {proj}\nSequence: {seq}\nSubject: {acq.get('SubID','N/A')}\n"
                    f"SeriesNumber: {acq.get('SeriesNumber','N/A')}\nStation: {acq.get('Station','N/A')}\n"
                    f"Acq Timestamp (DB): {acq.get('AcqDate','????')} {acq.get('AcqTime','????')}\n"
                    f"(DB used: {db_used})\n———\n"
                )
                if split_emails:
                    per_email_payloads.append((f"MRQART: NO TEMPLATE — {proj} / {seq}", body))
                else:
                    failures.append(body)
            continue

        if errors:
            if split_emails:
                subj = f"MRQART: Non-conforming — {proj} / {seq}"
                per_email_payloads.append((subj, format_one_failure(acq, ap, errors, db_used)))
            else:
                failures.append(format_one_failure(acq, ap, errors, db_used))

    # notify
    any_fail = False
    if not failures and not per_email_payloads:
        if not force_email:
            print("[info] All recent acquisitions conform (or none matched filters).")
            persist_report(results_for_web); return 0
        # forced summary (scanned >0 but 0 failures)
        since_str = since_arg or "yesterday"
        scanned = len(acqs_rows)
        subject = f"MRQART: Forced summary since {since_str} — 0 non-conforming (scanned={scanned})"
        body = (f"Header compliance check for acquisitions since {since_str}\n"
                f"Non-conforming count: 0\nScanned acquisitions in window: {scanned}\n\n"
                f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n— MRQART\n")
        for e in email_entries:
            ok = send_via_local_mail(subject, body, e["to"])
            print(f"[{'ok' if ok else 'fail'}] mailed {e['to']}"); any_fail |= (not ok)
        persist_report(results_for_web); return 0 if not any_fail else 7

    if not split_emails:
        since_str = since_arg or "yesterday"
        subject, body = summarize_failures(failures, since_str)
        for e in email_entries:
            ok = send_via_local_mail(subject, body, e["to"])
            print(f"[{'ok' if ok else 'fail'}] mailed {e['to']}"); any_fail |= (not ok)
    else:
        for subj, body in per_email_payloads:
            for e in email_entries:
                ok = send_via_local_mail(subj, body, e["to"])
                print(f"[{'ok' if ok else 'fail'}] mailed {e['to']}"); any_fail |= (not ok)

    persist_report(results_for_web)
    return 0 if not any_fail else 7

if __name__ == "__main__":
    raise SystemExit(main())

