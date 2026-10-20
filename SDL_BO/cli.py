"""Command line interface:  python -m SDL_BO <command> [options]

    init        write the round-1 design (candidates CSV)
    merge       add one round's measured wells (history format) to the history CSV
    suggest     read the history CSV, write the next round's candidates CSV
    report      print a summary of the history CSV
"""
import argparse
from pathlib import Path

import pandas as pd

from .campaign import seed_design, suggest_next_round
from .history import HistoryError
from .merge import MergeError, append_round_to_history
from .report import make_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="SDL_BO", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="write the round-1 design")
    init.add_argument("--out", default="candidates.csv", help="candidates CSV to write")
    init.add_argument("--force", action="store_true", help="overwrite --out if it already exists")

    merge = commands.add_parser("merge", help="add one round's measured wells to the history")
    merge.add_argument("--round-data", required=True, help="CSV of the round's measured wells, in history format")
    merge.add_argument("--history", default="history.csv", help="history CSV to append to (created if absent)")

    suggest = commands.add_parser("suggest", help="design the next round from the history")
    suggest.add_argument("--history", default="history.csv", help="history CSV to read")
    suggest.add_argument("--out", default="candidates.csv", help="candidates CSV to write (overwritten each round)")
    suggest.add_argument("--seed", type=int, default=0, help="seed for the random fallbacks (default 0)")

    report = commands.add_parser("report", help="summarize the history")
    report.add_argument("--history", default="history.csv", help="history CSV to read")
    return parser


def _run_init(args) -> None:
    out_path = Path(args.out)
    if out_path.exists() and not args.force:
        raise SystemExit(f"{out_path} already exists; pass --force to overwrite it")
    seed_design().to_csv(out_path, index=False)
    print(f"wrote {out_path}")


def _run_merge(args) -> None:
    round_rows = pd.read_csv(args.round_data)
    combined = append_round_to_history(args.history, round_rows)
    print(f"added {len(round_rows)} wells (round {int(round_rows['round'].iloc[0])}) to {args.history}; "
          f"it now has {len(combined)} wells")


def _run_suggest(args) -> None:
    candidates, info = suggest_next_round(args.history, seed=args.seed)
    candidates.to_csv(args.out, index=False)
    print(f"wrote {args.out}: round {info['round']}, kernels={info['kernels']}, "
          f"n_training_wells={info['n_training_wells']}")


def _run_report(args) -> None:
    print(make_report(args.history))


COMMANDS = {"init": _run_init, "merge": _run_merge,
            "suggest": _run_suggest, "report": _run_report}


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args)
    except (HistoryError, MergeError, FileNotFoundError) as error:
        raise SystemExit(f"error: {error}") from None  # a one-line message, not a traceback
