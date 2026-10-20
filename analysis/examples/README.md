# analysis/examples

Synthetic plate-reader data for developing and testing the analysis step. Everything here is fake and follows the
formats of `OT protocols/bo_bridge.py` and `analysis/qc_layout.py`.

## Files

- `fake_plate_reader.py`: the fake chemistry and export writers. Solvent and solute names are bo_bridge's (DMF, 2MeTHF, EtOAc, DMC, CPME, MeCN, iPrOAc; solutes S1-S4). Also imported by `SDL_BO/examples/make_examples.py`, `examples/toy_additive_pipeline.py` and `tests/`.
- `make_example_plates.py`: regenerates the round-1 files below from `OT protocols/examples/plate_map_round1.csv` (4 solutes × 24 wells, 1 DMF control + 23 conditions each).
- `make_toy_run.py`: builds a complete fake campaign folder (3 rounds by default: suggestions, plate maps, spectra, QC plates, plate logs, endpoint files, merged datasets) in seconds, without SDL_BO, for `analysis qc` and `analysis report`. `--fixed-wavelengths` exports only the solute peaks plus 700 nm.
- `reader_round1_plate{1,2,3}.csv`: full-spectrum exports of the 3 identical plates of round 1. Long table with columns `well`, `wavelength_nm` (200-800 nm, 1 nm step), `absorbance`.
- `reader_round1_blank.csv`: the same plate without solids (solvent background only), the older blank-plate route.
- `qc_plate_map_round1.csv`, `ot_input_round1_qc.csv`, `reader_round1_qc.csv`: the QC plate of round 1 (56 calibration + 40 blank wells), its robot CSV and its spectra.
- `plate_log_round1.csv`: fake shake-end-to-read minutes per plate.

## Fake chemistry

Each solute has one Gaussian band (S1 275 nm, S2 320 nm, S3 350 nm, S4 410 nm) on a UV-rising baseline with noise.
Band height = 1.2 × a "dissolved fraction" = fraction-weighted per-solvent dissolving power plus a synergy bonus for
balanced mixtures, capped at 1. DMF gives full dissolution. Calibration wells dissolve `min(loading, solubility)`
of the nominal mass, so their series bend over in poor solvents. Optional knobs (used by `make_toy_run.py`, off by
default): per-solute band heights, plate attack growing with the read delay, a reader ceiling of 3.5.

## Source of variations in the generated fake values

**How the numbers are made.** For each well on each plate, `fake_plate_reader.spectrum` computes a deterministic spectrum from the well's composition and solute: a baseline rising into the UV, plus a Gaussian band whose height is the fake "dissolved fraction" times the solute's band height, plus, in the synergy run only, a plate-attack term that grows with that plate's read delay. It then adds rng.normal(0, 0.004) at every wavelength, drawn fresh for every well, plate and round from one seeded generator. The blank or QC plate gets its own draws.

**Where the replicate spread comes from.** The dissolved fraction never varies: the same composition gives the same band on plate 1, 2 and 3 and in every round. So the plate-to-plate CV of about half a percent is purely reader noise. Each endpoint value is a single wavelength point, so its noise is 0.004 raw, roughly 0.0057 after subtracting a noisy blank, over a signal near 1.2 at the control.

**Where the cross-round variation comes from.** Three things. The DMF control has only three wells per round, so its mean carries about 0.3% noise, and because every value in a round is divided by it, the whole round shifts together. That is the drift Q2 shows and the reason the error model needed the normalisation term. In the synergy run, each plate's read delay is drawn at random, so the attack term differs slightly between plates and rounds. And re-tested mixtures are simply re-measured with new noise.

**What is not modelled.** No pipetting volume error, no variation in weighed solid mass, no dissolution kinetics or incomplete equilibration, no well-position or edge effects, no evaporation. The fake data is therefore an optimistic floor: real plate-to-plate CVs will be larger, and the QC checks have only been exercised against reader noise. If you want a more realistic noise floor to test against, I'd add optional knobs for volume error per dispense and mass error per well to fake_plate_reader, defaulting to zero so sdl_merge's tests keep passing.

## Running the analysis on these files

From the repo root in the `sdlhack` environment:

```bash
python -m analysis reduce --plate-map "OT protocols/examples/plate_map_round1.csv" \
  --reader analysis/examples/reader_round1_plate{1,2,3}.csv \
  --qc-reader analysis/examples/reader_round1_qc.csv --qc-map analysis/examples/qc_plate_map_round1.csv \
  --outdir runs/round1 --plots
python analysis/examples/make_toy_run.py --outdir runs/toy && python -m analysis qc --run runs/toy && python -m analysis report --run runs/toy
```
