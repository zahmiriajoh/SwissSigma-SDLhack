"""Toy run of the whole pipeline with additive fake chemistry: BO should home in on the best pure solvent.

    SDL_BO init/suggest -> bo_bridge layout -> fake spectra -> analysis reduce -> bo_bridge merge -> ...

Fake solubility of a mixture = sum over solvents of (fraction x that solvent's power for the solute), with no
synergy, and one solvent (DOMINANT) is best for every solute. The optimum is then 100% DOMINANT: the report's best
mixture must be the pure solvent and the exploit picks should move towards it.

How far they can move is capped by the hardware: one 25 mL trough per solvent feeds 3 plates x 4 solutes, so a
round's 23 conditions may hold at most ~1960 uL of any solvent (mean fraction 0.28). With that cap the BO instead
spends the whole DOMINANT budget on the DOMINANT-richest untested mixtures. `--one-plate` loosens the cap
(5880 uL) and shows the exploit picks themselves becoming DOMINANT-rich.

Run from the repo root in the `sdlhack` environment (~1 min per round on the 5 uL grid, ~10 s with --coarse):
    python examples/toy_additive_pipeline.py [--rounds 3] [--coarse] [--one-plate] [--dominant EtOH] [--outdir DIR]
Every file of every round (suggestions, robot CSV, plate map, spectra, endpoint exports, wavelengths, per-well
results, bo_dataset) is kept in --outdir (default examples/toy_additive_output/, tracked in git together with the
`analysis qc` / `report` outputs in its figures/ subfolder; rerun both after regenerating) for debugging the other
modules against. --coarse has few mixtures near a vertex, so its exploit picks drift away after a round or two.
Exit code 0 if the expectations hold, 1 otherwise.

Names, volumes and the zero-based numbering come from production/config.toml. The tracked outputs in
examples/toy_additive_output*/ predate that file: they use the earlier solvent names (2MeTHF, EtOAc, DMC, CPME, MeCN,
iPrOAc), solutes S1-S4 and 1-based numbering, and are kept as frozen records rather than regenerated.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "analysis" / "examples"), str(REPO / "SDL_BO" / "examples")]
import fake_plate_reader as fpr  # noqa: E402
import make_examples  # noqa: E402

from SDL_BO import space  # noqa: E402
from SDL_BO.report import make_report  # noqa: E402

DOMINANT_POWER, OTHER_POWERS = 0.9, [0.2, 0.35, 0.5, 0.6, 0.7]
MIN_EXPLOIT_FRACTION = 0.5  # of DOMINANT, averaged over the last round's exploit picks (when the budget allows)
MIN_BUDGET_USED = 0.9       # or: share of DOMINANT's trough budget the last round's suggestions use


def additive_chemistry(dominant: str) -> None:
    """Make fake_plate_reader additive (no synergy) with `dominant` the best solvent for every solute."""
    others = [s for s in fpr.GREEN_SOLVENTS if s != dominant]
    power = {solute: {space.REFERENCE_SOLVENT: 1.0, dominant: DOMINANT_POWER} for solute in fpr.PEAK_NM}
    for i, solute in enumerate(fpr.PEAK_NM):  # rotate the other powers so each solute ranks them differently
        power[solute].update(zip(others, OTHER_POWERS[i:] + OTHER_POWERS[:i]))
    fpr.POWER = pd.DataFrame(power).loc[fpr.ALL_SOLVENTS]
    fpr.SYNERGY = 0.0


def spectra_then_analysis(plate_map, round_number, workdir, rng):
    """Measure full spectra for every plate, then reduce them with `python -m analysis reduce`."""
    plates = range(make_examples.FIRST_PLATE, make_examples.FIRST_PLATE + make_examples.N_PLATES)
    readers = [workdir / f"reader_round{round_number}_plate{i}.csv" for i in plates]
    for path in readers:
        fpr.spectra_export(plate_map, rng).to_csv(path, index=False)
    blank = workdir / f"reader_round{round_number}_blank.csv"
    fpr.spectra_export(plate_map, rng, solids=False).to_csv(blank, index=False)
    subprocess.run([sys.executable, "-m", "analysis", "reduce", "--plate-map", workdir / f"plate_map_round{round_number}.csv",
                    "--reader", *readers, "--blank", blank, "--outdir", workdir], check=True, cwd=REPO, capture_output=True)
    return [workdir / f"endpoint_round{round_number}_plate{i}.csv" for i in plates], workdir / f"endpoint_round{round_number}_blank.csv"


def dominant_fraction_by_kind(out_dir, n_rounds, dominant) -> pd.DataFrame:
    """Mean fraction of `dominant` in each round's suggestions, split by condition kind."""
    rows = []
    for round_number in range(space.FIRST_ROUND + 1, space.FIRST_ROUND + n_rounds + 1):
        s = pd.read_csv(out_dir / f"suggestions_round{round_number}.csv")
        kind = s["condition_id"].str.extract(r"R\d+_([a-z]+)")[0].where(s["condition_id"].str.startswith(f"R{round_number}_"), "retest")
        rows.append(s.groupby(kind)[f"frac_{dominant}"].mean().rename(f"round {round_number}"))
    return pd.concat(rows, axis=1).round(2)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=3, help="measured rounds (default 3)")
    parser.add_argument("--coarse", action="store_true", help="50 uL grid instead of 5 uL: much faster, same behaviour")
    parser.add_argument("--dominant", default=space.GREEN_SOLVENTS[1], choices=space.GREEN_SOLVENTS)
    parser.add_argument("--one-plate", action="store_true", help="1 plate per round instead of 3: 3x the solvent budget")
    parser.add_argument("--outdir", default=REPO / "examples" / "toy_additive_output", help="where every file of the run goes")
    args = parser.parse_args(argv)
    if args.coarse:
        space.STEP_UL = 50
    if args.one_plate:
        space.N_PLATES = make_examples.N_PLATES = 1
    additive_chemistry(args.dominant)

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    dataset = make_examples.run_campaign(args.rounds, out, out, seed=0, make_readers=spectra_then_analysis)
    report = make_report(dataset)
    table = dominant_fraction_by_kind(out, args.rounds, args.dominant)
    last = pd.read_csv(out / f"suggestions_round{space.FIRST_ROUND + args.rounds}.csv")
    (out / "report.txt").write_text(report + "\n")

    print("\n" + report)
    print(f"\nMean fraction of {args.dominant} in the suggestions, by condition kind:\n{table}")
    best_is_pure = report.splitlines()[0].startswith(f"Best mixture: 100% {args.dominant} ")
    exploit_fraction = table.loc["exploit"].iloc[-1]
    budget_used = last[f"frac_{args.dominant}"].sum() * space.TOTAL_UL / space.solvent_budget_ul()
    pushed = exploit_fraction >= MIN_EXPLOIT_FRACTION or budget_used >= MIN_BUDGET_USED
    print(f"\nBest mixture is pure {args.dominant}: {best_is_pure}")
    print(f"Last round's exploit picks average {exploit_fraction:.2f} {args.dominant} (>= {MIN_EXPLOIT_FRACTION} wanted), "
          f"and the round uses {budget_used:.0%} of the {args.dominant} trough budget (>= {MIN_BUDGET_USED:.0%} wanted); "
          f"one of the two must hold: {pushed}")
    print("PASS" if best_is_pure and pushed else "FAIL")
    return 0 if best_is_pure and pushed else 1


if __name__ == "__main__":
    sys.exit(main())
