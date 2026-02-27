#!/usr/bin/env python3
"""
mrqart CLI entrypoint.

Commands:
  - daily-email (default): runs the daily email job (email_latest_flip.main)
  - seq-report: prints a per-sequence summary for a specific Project/SubID/SequenceName
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .email_latest_flip import main as daily_email_main
from .seq_report import parse_seq_path, render_seq_report


def _repo_root() -> Path:
    # mrqart/__main__.py -> mrqart/ -> repo root
    return Path(__file__).resolve().parents[1]


def _build_parser() -> argparse.ArgumentParser:
    repo = _repo_root()

    p = argparse.ArgumentParser(prog="mrqart", description="MRQART utilities")
    sub = p.add_subparsers(dest="cmd")

    # ---- daily-email
    sp_daily = sub.add_parser("daily-email", help="Run the daily header-compliance email (default)")
    sp_daily.add_argument(
        "--db",
        default=str(repo / "db.sqlite"),
        help="Path to db.sqlite (default: ./db.sqlite)",
    )
    sp_daily.add_argument(
        "--reporting",
        default=str(repo / "config" / "reporting.toml"),
        help="Path to reporting.toml (default: ./config/reporting.toml)",
    )
    sp_daily.add_argument(
        "--email-toml",
        default=str(repo / "config" / "email_settings.toml"),
        help="Path to email_settings.toml (default: ./config/email_settings.toml)",
    )
    sp_daily.add_argument(
        "--date",
        default=None,
        help="Override report date as YYYYMMDD or YYYY-MM-DD (default: yesterday)",
    )
    sp_daily.add_argument(
        "--print-email",
        action="store_true",
        default=False,
        help="Dry run: build the email and print to stdout instead of sending",
    )

    # ---- seq-report
    sp = sub.add_parser("seq-report", help="Quick summary for a specific Project/SubID/SequenceName")
    sp.add_argument(
        "--path",
        default=None,
        help="Slash-delimited Project/SubID/SequenceName, e.g. 'Brain^WPC-8409/20260206Sarpal1/mprage'",
    )
    sp.add_argument(
        "--db",
        default=str(repo / "db.sqlite"),
        help="Path to db.sqlite (default: ./db.sqlite)",
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
        help="Comma-separated list of marquee cols",
    )
    sp.add_argument(
        "--examples",
        type=int,
        default=0,
        help="Print first N example rows (default: 0)",
    )
    # backwards-compat hidden args
    sp.add_argument("--project", default=None, help=argparse.SUPPRESS)
    sp.add_argument("--subid", default=None, help=argparse.SUPPRESS)
    sp.add_argument("--sequence", dest="seqname", default=None, help=argparse.SUPPRESS)
    sp.add_argument("--seqname", dest="seqname", default=None, help=argparse.SUPPRESS)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Backwards compat: if no subcommand, run daily-email
    if not argv or argv[0] not in ("daily-email", "seq-report"):
        argv = ["daily-email"] + argv

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "seq-report":
        # Resolve project/subid/seqname from --path or individual hidden args
        if args.path:
            try:
                project, subid, seqname = parse_seq_path(args.path)
            except ValueError as e:
                parser.error(str(e))
            print("Parsed path:")
            print(f"  Project:  {project}")
            print(f"  SubID:    {subid}")
            print(f"  Sequence: {seqname}")
            print()
        elif args.project and args.subid and args.seqname:
            project, subid, seqname = args.project, args.subid, args.seqname
        else:
            parser.error("provide --path OR all of --project, --subid, --sequence")

        marquee_cols = [c.strip() for c in str(args.marquee).split(",") if c.strip()]
        report = render_seq_report(
            project=project,
            subid=subid,
            seqname=seqname,
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
            os.environ["MRQART_DATE"] = str(args.date)
        os.environ["MRQART_DB"] = str(args.db)
        os.environ["MRQART_REPORTING_TOML"] = str(args.reporting)
        os.environ["MRQART_EMAIL_TOML"] = str(args.email_toml)
        return int(daily_email_main(dry_run=args.print_email))

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
