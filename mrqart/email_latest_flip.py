#!/usr/bin/env python3
import os
import sys
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple

# --------- Config ---------
DEFAULT_ROOT = "/Volumes/Hera/Raw/MRprojects/Habit"
DEFAULT_PATTERN = "RewardedAntisaccade_704x75"

EMAIL_TOML = Path(__file__).resolve().parent.parent / "config" / "email_settings.toml"
DB_PATH = Path(__file__).resolve().parent.parent / "db.sqlite"
os.environ.setdefault("MRQART_DB", str(DB_PATH))

try:
    import tomllib as toml  # py3.11+
except Exception:
    import toml  # type: ignore

from mrqart.acq2sqlite import DBQuery
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


def most_recent_scan_dir(root: Path, contains: str) -> Optional[Path]:
    candidates = []
    try:
        for d0 in root.iterdir():
            if not d0.is_dir():
                continue
            for d1 in d0.iterdir():
                if not d1.is_dir():
                    continue
                for d2 in d1.iterdir():
                    if d2.is_dir() and contains in d2.name:
                        try:
                            candidates.append((d2.stat().st_mtime, d2))
                        except Exception:
                            pass
    except FileNotFoundError:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def pick_a_dicom(scan_dir: Path) -> Optional[Path]:
    for p in scan_dir.iterdir():
        if p.is_file() and (p.name.startswith("MR") or p.suffix.lower() in (".dcm", ".ima")):
            return p
    for p in scan_dir.rglob("*"):
        if p.is_file():
            return p
    return None


def get_flip_angle(hdr: Dict[str, Any]) -> Optional[float]:
    candidates = ("FlipAngle", "Flip Angle", "FA", "AcqFlipAngle", "ACQ Flip Angle")
    raw: Optional[str | float | int] = None
    for k in candidates:
        if k in hdr and hdr[k] is not None:
            raw = hdr[k]
            break
    if raw is None:
        return None
    try:
        return float(raw)
    except Exception:
        s = str(raw)
        num = "".join(ch for ch in s if ch.isdigit() or ch == "." or ch == "-")
        try:
            return float(num) if num else None
        except Exception:
            return None


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


def _as_float(x):
    try:
        return float(x)
    except Exception:
        return None


def _norm_str(x) -> Optional[str]:
    if x is None:
        return None
    import re
    s = re.sub(r"\s+", " ", str(x)).strip()
    return s.casefold()  # case/locale robust lowercase


def compare_against_template(hdr: Dict[str, Any], tmpl: Dict[str, Any]) -> Dict[str, str]:
    """
    Compare header vs template using DBQuery.CONSTS fields.
    - Numeric fields compare with tolerance
    - Strings compare case/whitespace-insensitively
    Returns {field: "expected X, got Y"}; empty dict means conforming.
    """
    errors: Dict[str, str] = {}

    # Map DB key
    keymap: Dict[str, Tuple[str, ...]] = {
        "FA": ("FlipAngle", "FA"),
        "TR": ("TR",),
        "TE": ("TE",),
        "iPAT": ("iPAT",),
        "Phase": ("Phase",),
        "SequenceType": ("SequenceType",),
        "PED_major": ("PED_major",),
        "Matrix": ("Matrix",),
        "PixelResol": ("PixelResol",),
        "BWP": ("BWP",),
        "BWPPE": ("BWPPE",),
        "TA": ("TA",),
        "FoV": ("FoV",),
        "Project": ("Project",),
        "SequenceName": ("SequenceName",),
        "Comments": ("Comments",),
    }

    for db_key in DBQuery.CONSTS:
        if db_key not in keymap:
            continue
        hdr_val = next((hdr.get(k) for k in keymap[db_key] if hdr.get(k) is not None), None)
        db_val = tmpl.get(db_key)

        hvf, dvf = _as_float(hdr_val), _as_float(db_val)
        if hvf is not None and dvf is not None:
            if abs(hvf - dvf) > 1e-3:
                errors[db_key] = f"expected {db_val}, got {hdr_val}"
        else:
            if _norm_str(hdr_val) != _norm_str(db_val):
                errors[db_key] = f"expected {db_val}, got {hdr_val}"

    return errors


# --------- Main ---------
def main() -> int:
    root = Path(os.environ.get("MRQART_ROOT", DEFAULT_ROOT))
    pattern = os.environ.get("MRQART_PATTERN", DEFAULT_PATTERN)

    try:
        email_entries = load_email_entries(EMAIL_TOML)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    if not email_entries:
        print(f"[error] No usable recipients in {EMAIL_TOML}", file=sys.stderr)
        return 2

    scan_dir = most_recent_scan_dir(root, pattern)
    if not scan_dir:
        print(f"[error] No scan dirs matching *{pattern}* under {root}", file=sys.stderr)
        return 3

    dcm = pick_a_dicom(scan_dir)
    if not dcm:
        print(f"[error] No files inside {scan_dir}", file=sys.stderr)
        return 4

    # Parse the DICOM header using the repo reader
    try:
        reader = TemplateChecker(context="RT").reader
        hdr = reader.read_dicom_tags(dcm)
    except Exception as e:
        print(f"[error] read_dicom_tags failed for {dcm}: {e}", file=sys.stderr)
        return 5

    # Pull expected template directly from DB
    project = hdr.get("Project", "%")
    seqname = hdr.get("SequenceName", "%")

    try:
        dbq = DBQuery(sqlite3.connect(str(DB_PATH)))
        tmpl_row = dbq.get_template(project, seqname)
    except Exception as e:
        print(f"[error] DBQuery.get_template failed: {e}", file=sys.stderr)
        tmpl_row = None

    if tmpl_row:
        tmpl = dict(tmpl_row)
        errors = compare_against_template(hdr, tmpl)
        conforms = (len(errors) == 0)
        conforms_str = "True" if conforms else "False"
        err_count = len(errors)
        err_text = "\n".join(f" - {k}: {v}" for k, v in errors.items()) or " - None"
        hint = ""
    else:
        conforms_str = "N/A (no template match)"
        err_count = 0
        err_text = " - None"
        hint = (
            "Hint: No template row found for this Project/SequenceName in DB. "
            "Check casing and naming conventions."
        )

    # Compose and send email
    fa = get_flip_angle(hdr)
    fa_text = f"{fa:g}°" if isinstance(fa, (int, float)) else str(fa)
    station = hdr.get("Station", "N/A")
    series = hdr.get("SeriesNumber", "N/A")
    project = hdr.get("Project", "N/A")
    seqname = hdr.get("SequenceName", "N/A")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_used = os.environ.get("MRQART_DB", str(DB_PATH))

    subject = f"MRQART: Latest {pattern} — conforms={conforms_str} — errors={err_count}"
    body = (
        "Header compliance check for latest scan\n"
        f"Pattern: {pattern}\n"
        f"Project: {project}\n"
        f"Conforms: {conforms_str}\n"
        f"Errors ({err_count}):\n{err_text}\n"
        f"{hint}\n\n"
        f"Flip Angle: {fa_text}\n"
        f"Station: {station}\n"
        f"Sequence: {seqname}\n"
        f"SeriesNumber: {series}\n\n"
        f"Scan dir: {scan_dir}\n"
        f"Sample file: {dcm.name}\n"
        f"Timestamp: {now}\n"
        f"(DB used: {db_used})\n"
        "— MRQART\n"
    )

    any_fail = False
    for e in email_entries:
        ok = send_via_local_mail(subject, body, e["to"])
        if ok:
            print(f"[ok] mailed {e['to']}")
        else:
            any_fail = True

    return 0 if not any_fail else 7


if __name__ == "__main__":
    raise SystemExit(main())

