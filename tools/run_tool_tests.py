#!/usr/bin/env python3
"""Run the supported Python tool tests with repository-local imports configured."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest


TOOLS_DIR = Path(__file__).resolve().parent
TESTS_DIR = TOOLS_DIR / "tests"
DEFAULT_PATTERN = "test_*.py"


def test_pattern(value: str) -> str:
    if not value or Path(value).name != value:
        raise argparse.ArgumentTypeError("pattern must be a filename glob, not a path")
    if not value.startswith("test_") or not value.endswith(".py"):
        raise argparse.ArgumentTypeError("pattern must match test_*.py")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover import-safe unittest modules under tools/tests/."
    )
    parser.add_argument(
        "--pattern",
        type=test_pattern,
        default=DEFAULT_PATTERN,
        help=f"test filename glob (default: {DEFAULT_PATTERN})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show each test name",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sys.path.insert(0, str(TOOLS_DIR))
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(TESTS_DIR),
        pattern=args.pattern,
        top_level_dir=str(TESTS_DIR),
    )
    result = unittest.TextTestRunner(
        verbosity=2 if args.verbose else 1,
        buffer=not args.verbose,
    ).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
