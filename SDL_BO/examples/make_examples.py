"""Run the closed loop for a few rounds with a fake plate reader and keep the files as examples.

    SDL_BO init/suggest -> bo_bridge layout -> fake plate reader -> bo_bridge merge -> SDL_BO suggest ...

Run from the repo root inside the `sdlhack` environment:  python SDL_BO/examples/make_examples.py [--rounds 3]
Also used by the tests as the end-to-end check that SDL_BO and bo_bridge speak the same formats.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
BO_BRIDGE = REPO / "OT protocols" / "bo_bridge.py"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "data" / "debug_analysis"))
from fake_plate_reader import endpoint_export, read_plate_map  # noqa: E402

from SDL_BO.campaign import seed_design, suggest_next_round  # noqa: E402

N_PLATES = 3


def bridge(*args) -> str:
    """Run a bo_bridge.py subcommand and return its output; fail loudly (with that output) on error."""
    result = subprocess.run([sys.executable, str(BO_BRIDGE), *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"bo_bridge {args[0]} failed:\n{result.stdout}{result.stderr}")
    return result.stdout


def run_round(round_number, suggestions_path, workdir, dataset_path, rng) -> None:
    """layout -> fake plates (+ blank) -> merge, all inside `workdir`."""
    bridge("layout", "--round", round_number, "--suggestions", suggestions_path, "--outdir", workdir)
    plate_map = read_plate_map(workdir / f"plate_map_round{round_number}.csv")
    readers = []
    for i in range(1, N_PLATES + 1):
        readers.append(workdir / f"reader_round{round_number}_plate{i}.csv")
        endpoint_export(plate_map, rng).to_csv(readers[-1], index=False)
    blank = workdir / f"reader_round{round_number}_blank.csv"
    endpoint_export(plate_map, rng, solids=False).to_csv(blank, index=False)
    bridge("merge", "--plate-map", workdir / f"plate_map_round{round_number}.csv",
           "--reader", *readers, "--blank", blank, "--dataset", dataset_path)


def run_campaign(n_rounds, out_dir, workdir, seed=0) -> Path:
    """Write suggestions_round1..N+1 and bo_dataset.csv into `out_dir`; returns the dataset path."""
    out_dir, workdir = Path(out_dir), Path(workdir)
    dataset = out_dir / "bo_dataset.csv"
    dataset.unlink(missing_ok=True)
    rng = np.random.default_rng(seed)
    suggestions = out_dir / "suggestions_round1.csv"
    seed_design().to_csv(suggestions, index=False)
    for round_number in range(1, n_rounds + 1):
        run_round(round_number, suggestions, workdir, dataset, rng)
        suggestions = out_dir / f"suggestions_round{round_number + 1}.csv"
        next_rows, info = suggest_next_round(dataset, seed=seed)
        next_rows.to_csv(suggestions, index=False)
        print(f"round {round_number} merged; incumbent score {info['incumbent_score']:.3f}; wrote {suggestions.name}")
    return dataset


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        run_campaign(args.rounds, Path(__file__).parent, tmp)
