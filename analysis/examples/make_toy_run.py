"""Build a complete fake campaign folder for developing and testing `analysis qc` / `analysis report`.

    bo_bridge grid/layout -> fake spectra (3 plates + QC plate + plate log) -> analysis reduce -> bo_bridge merge, per round

Later rounds use random (seeded) suggestions in SDL_BO's id scheme (R<n>_exploit00.., R<n>_explore00.., re-tests under
their first ids), so no Gaussian-process fitting is needed and the whole run takes seconds. Names and numbering come
from production/config.toml. The fake chemistry spans the reader's range on purpose (PLAN.md Q-b): the second solute
saturates in good solvents, the last sits near the noise floor, the first solute's band is hidden under acetone's UV
cut-off (so it is read on a shoulder and declared not measurable), and the plate-attacking solvents make blank wells
grow with the read delay.

Run from the repo root (prefix with `uv run`):
    python analysis/examples/make_toy_run.py --outdir runs/toy [--rounds 3] [--fixed-wavelengths] [--seed 0]
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "analysis" / "examples")]
import fake_plate_reader as fpr  # noqa: E402

from analysis.qc_layout import write_qc_layout  # noqa: E402
from analysis.spectra import read_plate_map  # noqa: E402
from production.config import FIRST_CONDITION, FIRST_PLATE, FIRST_ROUND, PLATE_ATTACKERS, SOLUTES, is_allowed  # noqa: E402

BO_BRIDGE = REPO / "OT protocols" / "bo_bridge.py"
N_PLATES = 3
N_EXPLOIT, N_EXPLORE, N_RETEST = 12, 6, 5
SOLVENT_BUDGET = 0.95 * 24000 / (300 * N_PLATES * 4)  # sum of a solvent's fractions over a round's conditions that one trough can feed
BAND_HEIGHTS = dict(zip(SOLUTES, [1.2, 2.6, 0.5, 0.06]))  # normal (but under acetone's cut-off), saturating, modest, near the noise
ATTACK_PER_MIN = {s: 4e-4 for s in PLATE_ATTACKERS}  # polystyrene attack by the solvents flagged in the config
CUTOFF_NM = {"DMF": 270, "acetone": 330}  # the two opaque solvents; the first solute's 275 nm band then sits under acetone's cut-off
PLATES = list(range(FIRST_PLATE, FIRST_PLATE + N_PLATES))
FIXED_NM = sorted(set(fpr.PEAK_NM.values()) | {700})  # solute peaks + a scattering reference


def run(*args):
    result = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=REPO)
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
    return result.stdout


def random_mixture(rng, n_solvents):
    """A 5 uL-grid mixture of n green solvents (no forbidden pair), as fractions."""
    solvents = rng.choice(fpr.GREEN_SOLVENTS, size=n_solvents, replace=False)
    while not is_allowed(solvents):
        solvents = rng.choice(fpr.GREEN_SOLVENTS, size=n_solvents, replace=False)
    units = rng.multinomial(60 - n_solvents, np.ones(n_solvents) / n_solvents) + 1  # 60 x 5 uL, each >= 5 uL
    return dict(zip(solvents, units / 60))


def suggestions(round_, outdir, rng) -> Path:
    """Round 1: bo_bridge grid. Later: perturbed top mixtures (exploit), random (explore), re-tests of the best."""
    path = outdir / f"suggestions_round{round_}.csv"
    if round_ == FIRST_ROUND:
        run(BO_BRIDGE, "grid", "--round", round_, "--seed", 0, "-o", path)
        return path
    shared = pd.read_csv(outdir / "bo_dataset_shared.csv")
    best = shared[shared["is_reference"] == 0].sort_values("obj_min_rel", ascending=False).drop_duplicates("condition_id")
    frac_cols = [f"frac_{s}" for s in fpr.GREEN_SOLVENTS]
    rows = [[row["condition_id"], *row[frac_cols].to_numpy(dtype=float)] for _, row in best.head(N_RETEST).iterrows()]

    def add_if_affordable(row):  # keep every solvent within what its trough can feed over the round; no forbidden pairs
        used = np.sum([r[1:] for r in rows + [row]], axis=0)
        present = [s for s, f in zip(fpr.GREEN_SOLVENTS, row[1:]) if f > 0]
        if (used <= SOLVENT_BUDGET).all() and is_allowed(present):
            rows.append(row)

    i = 0
    while sum(r[0].startswith(f"R{round_}_exploit") for r in rows) < N_EXPLOIT and i < 10 * N_EXPLOIT:
        base = best.iloc[i % min(3, len(best))][frac_cols].to_numpy(dtype=float) * 60  # a top mixture nudged by 5 uL steps
        for _ in range(1 + i // 3):  # move 5 uL between solvents, never above 3 solvents in the mixture
            present = np.flatnonzero(base > 0)
            donor = rng.choice(present[base[present] > 1])
            taker = rng.choice(present if len(present) >= 3 else np.arange(len(base)))
            base[donor] -= 1
            base[taker] += 1
        i += 1
        add_if_affordable([f"R{round_}_exploit{sum(r[0].startswith(f'R{round_}_exploit') for r in rows) + FIRST_CONDITION:02d}", *(base / 60)])
    while sum(r[0].startswith(f"R{round_}_explore") for r in rows) < N_EXPLORE:
        mix = random_mixture(rng, rng.integers(2, 4))
        add_if_affordable([f"R{round_}_explore{sum(r[0].startswith(f'R{round_}_explore') for r in rows) + FIRST_CONDITION:02d}", *(mix.get(s, 0.0) for s in fpr.GREEN_SOLVENTS)])
    df = pd.DataFrame(rows, columns=["condition_id"] + frac_cols).round(4).drop_duplicates(frac_cols)
    df.to_csv(path, index=False)
    return path


def measure(round_, outdir, rng, fixed):
    """Fake spectra for the 3 sample plates, the QC plate and the plate log."""
    plate_map = read_plate_map(outdir / f"plate_map_round{round_}.csv")
    qc_map = write_qc_layout(plate_map, outdir)
    log = fpr.plate_log([*PLATES, "qc"], rng)
    log.to_csv(outdir / f"plate_log_round{round_}.csv", index=False)
    delays = dict(zip(log["plate"].astype(str), log["read_delay_min"]))
    exports = [(f"reader_round{round_}_plate{p}.csv", fpr.spectra_export(plate_map, rng, delay_min=delays[str(p)])) for p in PLATES]
    exports.append((f"reader_round{round_}_qc.csv", fpr.qc_export(qc_map, rng, delay_min=delays["qc"])))
    for name, df in exports:
        (fpr.fixed_wavelength_export(df, FIXED_NM) if fixed else df).to_csv(outdir / name, index=False)


def one_round(round_, outdir, rng, fixed):
    sug = suggestions(round_, outdir, rng)
    run(BO_BRIDGE, "layout", "--round", round_, "--suggestions", sug, "--outdir", outdir)
    measure(round_, outdir, rng, fixed)
    readers = [outdir / f"reader_round{round_}_plate{p}.csv" for p in PLATES]
    run("-m", "analysis", "reduce", "--plate-map", outdir / f"plate_map_round{round_}.csv", "--reader", *readers,
        "--qc-reader", outdir / f"reader_round{round_}_qc.csv", "--qc-map", outdir / f"qc_plate_map_round{round_}.csv", "--outdir", outdir)
    endpoints = [outdir / f"endpoint_round{round_}_plate{p}.csv" for p in PLATES]
    run(BO_BRIDGE, "merge", "--plate-map", outdir / f"plate_map_round{round_}.csv", "--reader", *endpoints,
        "--blank", outdir / f"endpoint_round{round_}_blank.csv", "--dataset", outdir / "bo_dataset.csv")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--fixed-wavelengths", action="store_true", help=f"export only {FIXED_NM} nm instead of full spectra")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    fpr.BAND_HEIGHTS.update(BAND_HEIGHTS)
    fpr.ATTACK_PER_MIN.update(ATTACK_PER_MIN)
    fpr.CUTOFF_NM.update({k: v for k, v in CUTOFF_NM.items() if k in fpr.ALL_SOLVENTS})
    rng = np.random.default_rng(args.seed)
    for r in range(FIRST_ROUND, FIRST_ROUND + args.rounds):
        one_round(r, outdir, rng, args.fixed_wavelengths)
        print(f"round {r} done")
    print(f"toy run in {outdir}: now `python -m analysis qc --run {outdir}` and `python -m analysis report --run {outdir}`")


if __name__ == "__main__":
    main()
