"""CLI entry point for the parser service.

Usage:
    python -m app.parser                 # normal polling mode
    python -m app.parser --reset-offset  # reset offset to 0, then poll
    python -m app.parser --start-from-beginning  # alias for --reset-offset
"""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="ANLA Pricing Parser Service")
    parser.add_argument(
        "--reset-offset",
        action="store_true",
        help="Reset the parser offset to 0 and reprocess all events.",
    )
    parser.add_argument(
        "--start-from-beginning",
        action="store_true",
        help="Alias for --reset-offset.",
    )
    args = parser.parse_args()

    reset = args.reset_offset or args.start_from_beginning

    # Import here to avoid import-time side effects
    from app.parser.service import run

    run(reset_offset_flag=reset)


if __name__ == "__main__":
    main()
