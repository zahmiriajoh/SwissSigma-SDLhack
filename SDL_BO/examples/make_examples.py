"""Run the closed loop for a few rounds with a fake plate reader and keep the files as examples.

    SDL_BO init/suggest -> bo_bridge layout -> fake plate reader -> bo_bridge merge -> SDL_BO suggest ...

Run from the repo root with `uv run`:  python SDL_BO/examples/make_examples.py [--rounds 3]
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
sys.path.insert(0, str(REPO / "analysis" / "examples"))
from fake_plate_reader import endpoint_export, read_plate_map  # noqa: E402
from production import config  # noqa: E402

from SDL_BO import space  # noqa: E402
from SDL_BO.campaign import seed_design, suggest_next_round  # noqa: E402

N_PLATES = space.N_PLATES  # identical plates per round; the toy pipeline example sets this to 1
FIRST_ROUND, FIRST_PLATE = space.FIRST_ROUND, config.FIRST_PLATE


def bridge(*args) -> str:
    """Run a bo_bridge.py subcommand and return its output; fail loudly (with that output) on error."""
    result = subprocess.run([sys.executable, str(BO_BRIDGE), *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"bo_bridge {args[0]} failed:\n{result.stdout}{result.stderr}")
    return result.stdout


def endpoint_readers(plate_map, round_number, workdir, rng):
    """Fake "already reduced" plate-reader files: (plate paths, blank path), one absorbance per well."""
    readers = []
    for i in range(FIRST_PLATE, FIRST_PLATE + N_PLATES):
        readers.append(workdir / f"reader_round{round_number}_plate{i}.csv")
        endpoint_export(plate_map, rng).to_csv(readers[-1], index=False)
    blank = workdir / f"reader_round{round_number}_blank.csv"
    endpoint_export(plate_map, rng, solids=False).to_csv(blank, index=False)
    return readers, blank


def run_round(round_number, suggestions_path, workdir, dataset_path, rng, make_readers=endpoint_readers) -> None:
    """layout -> measure the plates (`make_readers`) -> merge, all inside `workdir`."""
    plate_map_path = workdir / f"plate_map_round{round_number}.csv"
    bridge("layout", "--round", round_number, "--suggestions", suggestions_path, "--outdir", workdir, "--plates", N_PLATES)
    readers, blank = make_readers(read_plate_map(plate_map_path), round_number, workdir, rng)
    bridge("merge", "--plate-map", plate_map_path, "--reader", *readers, "--blank", blank, "--dataset", dataset_path)


def run_campaign(n_rounds, out_dir, workdir, seed=0, make_readers=endpoint_readers) -> Path:
    """Write suggestions for rounds FIRST_ROUND..FIRST_ROUND+N and bo_dataset.csv into `out_dir`; returns the dataset path."""
    out_dir, workdir = Path(out_dir), Path(workdir)
    dataset = out_dir / "bo_dataset.csv"
    dataset.unlink(missing_ok=True)
    rng = np.random.default_rng(seed)
    suggestions = out_dir / f"suggestions_round{FIRST_ROUND}.csv"
    seed_design().to_csv(suggestions, index=False)
    for round_number in range(FIRST_ROUND, FIRST_ROUND + n_rounds):
        run_round(round_number, suggestions, workdir, dataset, rng, make_readers)
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
