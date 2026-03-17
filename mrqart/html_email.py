#!/usr/bin/env python3
"""
HTML summary email with full dashboard attachment.

Controlled by MRQART_HTML_EMAIL_TOML env var.
If not set, nothing is sent.

"""

from __future__ import annotations

import os
import subprocess
from email.header import Header
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .email_latest_flip import (
    SeqKey,
    SeqSummary,
    Totals,
    format_expected_got,
)

try:
    import tomllib as toml
except Exception:
    import toml  # type: ignore


def load_html_email_entries(toml_path: Path) -> List[Dict[str, str]]:
    """Load HTML email recipients from toml."""
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


def build_html_body(
    *,
    date_label: str,
    seq_summary: Dict[SeqKey, SeqSummary],
    missing_templates: Dict[SeqKey, Dict[str, Any]],
    totals: Totals,
    physicist_by_project: Mapping[str, Optional[str]],
    marquee_cols: List[str],
) -> str:
    """Build a condensed HTML email body."""
    from collections import defaultdict

    status_emoji = (
        "✅"
        if (totals.total_nonconforming == 0 and totals.mia_actionable == 0)
        else "❌"
    )

    # group nonconforming by project
    by_project: Dict[str, List[SeqKey]] = defaultdict(list)
    for key in sorted(seq_summary.keys()):
        if seq_summary[key].nonconforming > 0:
            by_project[key[0]].append(key)

    rows_html = ""
    for project in sorted(by_project.keys()):
        physicist = physicist_by_project.get(project) or ""
        physicist_str = f" &mdash; <em>{physicist}</em>" if physicist else ""
        project_rows = ""
        for key in by_project[project]:
            summary = seq_summary[key]
            _, subid, seqname = key
            top_errors = sorted(
                summary.mismatch_counts.items(), key=lambda kv: kv[1], reverse=True
            )
            error_lines = [
                format_expected_got(col, exp, got)
                for (col, exp, got), _ in top_errors
                if col in set(marquee_cols)
            ]
            if not error_lines:
                continue
            errors_html = "".join(f"<li>{e}</li>" for e in error_lines)
            project_rows += f"""
        <tr>
            <td style="padding:8px 12px;color:#94a3b8;">{subid}</td>
            <td style="padding:8px 12px;">{seqname}</td>
            <td style="padding:8px 12px;"><ul style="margin:0;padding-left:16px;">{errors_html}</ul></td>
        </tr>"""
        if not project_rows:
            continue
        rows_html += f"""
        <tr><td colspan="3" style="background:#1e293b;padding:8px 12px;font-weight:600;color:#60a5fa;">
            {project}{physicist_str}
        </td></tr>"""
        rows_html += project_rows

    html = f"""<!doctype html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;font-family:system-ui,sans-serif;background:#0b1020;color:#e5e7eb;">
<div style="max-width:900px;margin:0 auto;padding:20px;">

<h2 style="color:#60a5fa;margin-bottom:4px;">
    {status_emoji} MRQART Header Compliance — {date_label}
</h2>
<p style="color:#94a3b8;margin-top:0;">
    {totals.total_nonconforming} nonconforming / {totals.total_checked} checked
    ({totals.total_seen_today} total acquisitions)
</p>

{"<p style='color:#10b981;'>✅ All sequences conform.</p>" if totals.total_nonconforming == 0 else f'''
<table style="width:100%;border-collapse:collapse;background:#11162a;border-radius:8px;overflow:hidden;">
    <thead>
        <tr style="background:#0d1326;color:#94a3b8;font-size:12px;">
            <th style="padding:8px 12px;text-align:left;">Subject</th>
            <th style="padding:8px 12px;text-align:left;">Sequence</th>
            <th style="padding:8px 12px;text-align:left;">Errors</th>
        </tr>
    </thead>
    <tbody>
        {rows_html}
    </tbody>
</table>'''}

<p style="color:#94a3b8;font-size:12px;margin-top:20px;">
    Full interactive report attached. — MRQART
</p>
</div>
</body>
</html>"""
    return html


def send_html_email(
    *,
    subject: str,
    html_body: str,
    attachment_path: Optional[Path],
    from_addr: str,
    to_addr: str,
    smtp_host: str,
    smtp_port: int = 25,
) -> bool:
    """Send HTML email using local mail command."""
    if os.environ.get("DRYRUN"):
        print(f"DRYRUN - not sending HTML email to {to_addr}")
        return True
    try:
        subprocess.run(
            [
                "mail",
                "-s",
                subject.encode("ascii", "ignore").decode(),
                "-a",
                "Content-Type: text/html",
                to_addr,
            ],
            input=html_body.encode("utf-8"),
            check=True,
        )
        return True
    except Exception as e:
        print(f"[warn] HTML email send failed to {to_addr}: {e}")
        return False
