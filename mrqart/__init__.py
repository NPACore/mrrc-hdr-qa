import argparse
import sys

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mrqart",
        description=(
            "MRQArt — MRI Quality Assurance Reporting Tool\n\n"
            "Usage:\n"
            "  python -m mrqart        # run the package directly\n"
            "  python -m mrqart.email_latest_flip  # run the flip-angle email check\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--version", action="version", version="MRQArt 0.1.0"
    )

    parser.add_argument(
        "--check-flip",
        action="store_true",
        help="Run the flip-angle compliance email check (same as python -m mrqart.email_latest_flip)",
    )

    args = parser.parse_args()

    if args.check_flip:
        from .email_latest_flip import main as flip_check
        sys.exit(flip_check())
    else:
        parser.print_help()

