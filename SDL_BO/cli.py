"""Command line interface:  python -m SDL_BO <command> [options]

    init      write the round-1 suggestions CSV (for `bo_bridge.py layout`)
    suggest   read bo_dataset.csv (from `bo_bridge.py merge`), write the next round's suggestions CSV
    report    print a summary of bo_dataset.csv
"""
import argparse
from pathlib import Path

from .campaign import seed_design, suggest_next_round
from .dataset import DatasetError
from .report import make_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="SDL_BO", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="write the round-1 suggestions")
    init.add_argument("--out", default="suggestions_round1.csv")
    init.add_argument("--force", action="store_true", help="overwrite --out if it exists")

    suggest = commands.add_parser("suggest", help="design the next round from bo_dataset.csv")
    suggest.add_argument("--dataset", default="bo_dataset.csv", help="bo_dataset.csv written by bo_bridge.py merge")
    suggest.add_argument("--out", help="suggestions CSV to write (default suggestions_round<N>.csv)")
    suggest.add_argument("--seed", type=int, default=0, help="seed for the random fallbacks")

    report = commands.add_parser("report", help="summarize bo_dataset.csv")
    report.add_argument("--dataset", default="bo_dataset.csv")
    return parser


def _run_init(args) -> None:
    out = Path(args.out)
    if out.exists() and not args.force:
        raise SystemExit(f"{out} already exists; pass --force to overwrite it")
    seed_design().to_csv(out, index=False)
    print(f"wrote {out}")


def _run_suggest(args) -> None:
    suggestions, info = suggest_next_round(args.dataset, seed=args.seed)
    out = Path(args.out or f"suggestions_round{info['round']}.csv")
    suggestions.to_csv(out, index=False)
    print(f"wrote {out}: round {info['round']}, {len(suggestions)} conditions, "
          f"incumbent score {info['incumbent_score']:.3f}, kernels={info['kernels']}")


def _run_report(args) -> None:
    print(make_report(args.dataset))


COMMANDS = {"init": _run_init, "suggest": _run_suggest, "report": _run_report}


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args)
    except (DatasetError, ValueError, FileNotFoundError) as error:
        raise SystemExit(f"error: {error}") from None  # a one-line message, not a traceback
