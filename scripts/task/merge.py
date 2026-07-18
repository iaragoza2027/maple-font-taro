from __future__ import annotations

import argparse

from scripts.merge_sans_serif_font import main as merge_main


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]):
    parser = subparsers.add_parser("merge", help="Merge and instantiate fonts")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove temporary merge artifacts after completion",
    )
    return parser


def run(args: argparse.Namespace) -> None:
    merge_main(cleanup=args.cleanup)
