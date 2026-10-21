# analysis/examples

Synthetic plate-reader data for developing and testing the analysis step. Everything here is fake. The committed reader exports are
CSVs that `analysis reduce` reads directly; the real reader saves `.xlsx` workbooks (Tecan i-control export, format in
`production/README.md`), which `fake_plate_reader.write_plate_reader_xlsx` reproduces row for row for the tests. The other files
follow `OT protocols/bo_bridge.py`.

## Files

- `fake_plate_reader.py`: the fake chemistry and export writers. Solvent and solute names come from `production/config.toml` (DMF, acetone, EtOH, iPrOH, water, iPrOAc, tBuOAc; Glutarimide, Boc-hydroxyproline, Phthalimide, Succinimide); bands and dissolving powers are invented. Also imported by `SDL_BO/examples/make_examples.py`, `examples/toy_additive_pipeline.py` and `tests/`.
- `make_example_plates.py`: regenerates the round-0 files below from `OT protocols/examples/plate_map_round0.csv` (4 solutes × 24 wells, 1 DMF control + 23 conditions each; numbering from zero as in the config).
- `make_toy_run.py`: builds a complete fake campaign folder (3 rounds by default: suggestions, plate maps, spectra, plate logs, endpoint files, merged datasets) in seconds, without SDL_BO, for `analysis qc` and `analysis report`. It reads each fake solute at its known peak (no blanks, so nothing else fixes the wavelength). `--fixed-wavelengths` exports only the solute peaks plus 700 nm.
- `reader_round0_plate{0,1,2}.csv`: full-spectrum exports of the 3 identical plates of round 0. As a `;`-separated CSV with decimal commas, one row per well under a `Wavel.` header, 200-700 nm in 5 nm steps (`fake_plate_reader.write_plate_reader_csv`; a hand-made form `run_bo.sh` also accepts). The reader itself saves `.xlsx` workbooks; `fake_plate_reader.write_plate_reader_xlsx` writes that layout, used by `tests/test_reader_xlsx.py` and the campaign test.
- `reader_round0_solvents.csv`: the solvent blank plate after round 0, pure-solvent wells A1-G1 (DMF, acetone, EtOH, iPrOH, water, iPrOAc, tBuOAc) for `--solvent-blanks`; later rounds add a column each (A2-G2, ...).
- `reader_round0_blank.csv`: the same plate without solids (solvent background only), the older full blank-plate route; the tests check the predicted blank against it.
- `plate_log_round0.csv`: fake shake-end-to-read minutes per plate.

## Fake chemistry

Each solute has one Gaussian band (Glutarimide 275 nm, Boc-hydroxyproline 350 nm, Phthalimide 295 nm, Succinimide 410 nm; invented) on a UV-rising baseline with noise.
Band height = 1.2 × a "dissolved fraction" = fraction-weighted per-solvent dissolving power plus a synergy bonus for
balanced mixtures, capped at 1. DMF gives full dissolution. Optional knobs (used by `make_toy_run.py`, off by
default): per-solute band heights, plate attack growing with the read delay, a reader ceiling of 3.5.

## Source of variations in the generated fake values

**How the numbers are made.** For each well on each plate, `fake_plate_reader.spectrum` computes a deterministic spectrum from the well's composition and solute: a baseline rising into the UV, plus a Gaussian band whose height is the fake "dissolved fraction" times the solute's band height, plus, in the synergy run only, a plate-attack term that grows with that plate's read delay. It then adds rng.normal(0, 0.004) at every wavelength, drawn fresh for every well, plate and round from one seeded generator. The blank plate gets its own draws.

**Where the replicate spread comes from.** The dissolved fraction never varies: the same composition gives the same band on plate 1, 2 and 3 and in every round. So the plate-to-plate CV of about half a percent is purely reader noise. Each endpoint value is a single wavelength point, so its noise is 0.004 raw, roughly 0.0057 after subtracting a noisy blank, over a signal near 1.2 at the control.

**Where the cross-round variation comes from.** Three things. The DMF control has only three wells per round, so its mean carries about 0.3% noise, and because every value in a round is divided by it, the whole round shifts together. That is the drift Q2 shows and the reason the error model needed the normalisation term. In the synergy run, each plate's read delay is drawn at random, so the attack term differs slightly between plates and rounds. And re-tested mixtures are simply re-measured with new noise.

**What is not modelled.** No pipetting volume error, no variation in weighed solid mass, no dissolution kinetics or incomplete equilibration, no well-position or edge effects, no evaporation. The fake data is therefore an optimistic floor: real plate-to-plate CVs will be larger, and the QC checks have only been exercised against reader noise. If you want a more realistic noise floor to test against, I'd add optional knobs for volume error per dispense and mass error per well to fake_plate_reader, defaulting to zero so sdl_merge's tests keep passing.

## Running the analysis on these files

From the repo root, after `bash setup.sh` (prefix with `uv run`):

```bash
python -m analysis reduce --plate-map "OT protocols/examples/plate_map_round0.csv" \
  --reader analysis/examples/reader_round0_plate{0,1,2}.csv \
  --solvent-blanks analysis/examples/reader_round0_solvents.csv \
  --outdir runs/round0 --plots
python analysis/examples/make_toy_run.py --outdir runs/toy && python -m analysis qc --run runs/toy && python -m analysis report --run runs/toy
```

The three tracked campaigns under `examples/toy_*_output/` were generated before `production/config.toml` existed and
keep the earlier fake names (S1–S4, 2MeTHF…) and 1-based numbering as frozen records; `analysis qc` and `report` still
read them.
