"""Command line interface:  python -m SDL_BO <command> [options]

    init      write the first round's suggestions CSV (for `bo_bridge.py layout`)
    suggest   read bo_dataset.csv (from `bo_bridge.py merge`), write the next round's suggestions CSV
              (--branch: one trajectory per arm of production/config.toml, a `solute` column puts each on its plate blocks)
    report    print a summary of bo_dataset.csv (--branch: one summary per arm)
"""
import argparse
from pathlib import Path

from . import space
from production.config import ARMS

from .campaign import seed_design, suggest_arms, suggest_next_round
from .dataset import DatasetError
from .report import make_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="SDL_BO", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="write the first round's suggestions")
    init.add_argument("--out", default=f"suggestions_round{space.FIRST_ROUND}.csv")
    init.add_argument("--force", action="store_true", help="overwrite --out if it exists")

    suggest = commands.add_parser("suggest", help="design the next round from bo_dataset.csv")
    suggest.add_argument("--dataset", default="bo_dataset.csv", help="bo_dataset.csv written by bo_bridge.py merge")
    suggest.add_argument("--out", help="suggestions CSV to write (default suggestions_round<N>.csv)")
    suggest.add_argument("--seed", type=int, default=0, help="seed for the random fallbacks")
    suggest.add_argument("--branch", action="store_true", help="design every arm of production/config.toml separately")

    report = commands.add_parser("report", help="summarize bo_dataset.csv")
    report.add_argument("--dataset", default="bo_dataset.csv")
    report.add_argument("--branch", action="store_true", help="one summary per arm of production/config.toml")
    return parser


def _run_init(args) -> None:
    out = Path(args.out)
    if out.exists() and not args.force:
        raise SystemExit(f"{out} already exists; pass --force to overwrite it")
    seed_design().to_csv(out, index=False)
    print(f"wrote {out}")


def _print_info(label, info) -> None:
    print(f"{label}round {info['round']}: incumbent score {info['incumbent_score']:.3f}, kernels={info['kernels']}")
    if info["unmeasurable"]:
        print(f"  not scored (analysis reduce flagged them not measurable): {', '.join(info['unmeasurable'])}")


def _run_suggest(args) -> None:
    if args.branch:
        if not ARMS:
            raise ValueError("--branch needs [[arms]] in production/config.toml")
        suggestions, infos = suggest_arms(args.dataset, seed=args.seed)
        round_ = next(iter(infos.values()))["round"]
    else:
        suggestions, info = suggest_next_round(args.dataset, seed=args.seed)
        infos, round_ = {"": info}, info["round"]
    out = Path(args.out or f"suggestions_round{round_}.csv")
    suggestions.to_csv(out, index=False)
    print(f"wrote {out}: round {round_}, {len(suggestions)} rows")
    for arm, info in infos.items():
        _print_info(f"  [{arm}] " if arm else "  ", info)


def _run_report(args) -> None:
    if not args.branch:
        print(make_report(args.dataset))
        return
    for arm, arm_solutes in ARMS.items():
        print(f"== Arm {arm} ({', '.join(arm_solutes)})\n{make_report(args.dataset, arm_solutes)}\n")


COMMANDS = {"init": _run_init, "suggest": _run_suggest, "report": _run_report}


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args)
    except (DatasetError, ValueError, FileNotFoundError) as error:
        raise SystemExit(f"error: {error}") from None  # a one-line message, not a traceback
