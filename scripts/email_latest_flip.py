#!/usr/bin/env python3
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_ROOT = "/Volumes/Hera/Raw/MRprojects/Habit"
DEFAULT_PATTERN = "RewardedAntisaccade_704x75"

EMAIL_TOML = Path(__file__).resolve().parent.parent / "config" / "email_settings.toml"

try:
    import tomllib as toml  # Python 3.11+
except Exception:  # py3.10 fallback
    import toml  # type: ignore


def load_email_entries(toml_path: Path) -> List[Dict[str, str]]:
    """
    Return a list of {from, to} entries (one per recipient) read from [[emails]].
    """
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
    """
    Scan three levels deep: root/YYYY.MM.DD-*/SUBID_YYYYMMDD/<scan dirs>
    Pick the newest dir whose name contains the pattern.
    """
    candidates = []
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
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def pick_a_dicom(scan_dir: Path) -> Optional[Path]:
    """Grab a likely DICOM file from the scan folder."""
    for p in scan_dir.iterdir():
        if p.is_file() and (
            p.name.startswith("MR") or p.suffix.lower() in (".dcm", ".ima")
        ):
            return p
    for p in scan_dir.rglob("*"):
        if p.is_file():
            return p
    return None


def extract_flip_angle(dicom_path: Path) -> Optional[float]:
    """
    Use AFNI 'dicom_hdr' and parse lines like:
    '... // ACQ Flip Angle//60'
    Split by '//' and take the 3rd field.
    """
    try:
        out = subprocess.check_output(
            ["dicom_hdr", str(dicom_path)], text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        return None
    for line in out.splitlines():
        if "Flip Angle" in line:
            parts = line.split("//")
            if len(parts) >= 3:
                raw = parts[2].strip()
                num = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
                if num:
                    try:
                        return float(num)
                    except ValueError:
                        return None
    return None


def send_via_local_mail(subject: str, body: str, recipient: str) -> bool:
    """
    Send using the local 'mail'
    """
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
        print(
            f"[error] No scan dirs matching *{pattern}* under {root}", file=sys.stderr
        )
        return 3

    dcm = pick_a_dicom(scan_dir)
    if not dcm:
        print(f"[error] No files inside {scan_dir}", file=sys.stderr)
        return 4

    fa = extract_flip_angle(dcm)
    if fa is None:
        print(f"[error] Could not parse Flip Angle from {dcm}", file=sys.stderr)
        return 5

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"MRQART: Latest RewardedAntisaccade FlipAngle = {fa:g}°"
    body = (
        f"Latest flip angle: {fa:g}°\n"
        f"Scan dir: {scan_dir}\n"
        f"Sample file: {dcm.name}\n"
        f"Timestamp: {now}\n"
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
