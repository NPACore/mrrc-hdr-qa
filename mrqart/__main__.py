#!/usr/bin/env python3
"""
mrqart CLI entrypoint.

Commands:
  - daily-email (default): runs the daily email job (email_latest_flip.main)
  - seq-report: prints a per-sequence summary for a specific Project/SubID/SequenceName
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .email_latest_flip import main as daily_email_main
from .seq_report import render_seq_report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mrqart", description="MRQART utilities")
    sub = p.add_subparsers(dest="cmd")

    sp_daily = sub.add_parser("daily-email", help="Run the daily header-compliance email (default)")
    sp_daily.add_argument("--db", default="db.sqlite", help="Path to db.sqlite (default: db.sqlite)")
    sp_daily.add_argument(
        "--reporting",
        default="config/reporting.toml",
        help="Path to reporting.toml (default: config/reporting.toml)",
    )
    sp_daily.add_argument(
        "--email-toml",
        default="config/email_settings.toml",
        help="Path to email_settings.toml (default: config/email_settings.toml)",
    )
    sp_daily.add_argument(
        "--date",
        default=None,
        help="Override report date as YYYYMMDD or YYYY-MM-DD (default: yesterday)",
    )

    # ---- seq-report
    sp = sub.add_parser("seq-report", help="Quick summary for a specific Project/SubID/SequenceName")
    sp.add_argument("--project", required=True, help="Project, e.g. Brain^WPC-8409")
    sp.add_argument("--subid", required=True, help="SubID, e.g. 20260206Sarpal1")
    sp.add_argument("--sequence", required=True, help="SequenceName, e.g. BoleroSlc15Fov216_thk3mm_tra")
    sp.add_argument(
        "--db",
        default="db.sqlite",
        help="Path to db.sqlite (default: db.sqlite)",
    )
    sp.add_argument(
        "--max-series",
        type=int,
        default=200,
        help="Ignore series numbers > this (default: 200)",
    )
    sp.add_argument(
        "--marquee",
        default="TR,TE,FA,TA,FoV,Matrix,PixelResol,BWP,BWPPE,SequenceType,Comments",
        help="Comma-separated list of marquee cols (default: TR,TE,FA,TA,FoV,Matrix,PixelResol,BWP,BWPPE,SequenceType,Comments)",
    )
    sp.add_argument(
        "--examples",
        type=int,
        default=0,
        help="Print first N example rows (default: 0)",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Backwards compat: if no subcommand, run daily-email
    if not argv or (argv and not argv[0].startswith("-") and argv[0] not in ("daily-email", "seq-report")):
        argv = ["daily-email"] + argv

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "seq-report":
        marquee_cols = [c.strip() for c in str(args.marquee).split(",") if c.strip()]
        report = render_seq_report(
            project=args.project,
            subid=args.subid,
            seqname=args.sequence,
            db_path=Path(args.db),
            max_series=args.max_series,
            marquee_cols=marquee_cols,
            examples=args.examples,
        )
        print(report)
        return 0

    # default: daily-email
    if args.cmd in (None, "daily-email"):
        if args.date:
            import os

            os.environ["MRQART_DATE"] = str(args.date)
        import os

        os.environ["MRQART_DB"] = str(args.db)
        os.environ["MRQART_REPORTING_TOML"] = str(args.reporting)

        return int(daily_email_main())

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

