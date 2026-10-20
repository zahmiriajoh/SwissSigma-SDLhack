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

## Running the analysis on these files

From the repo root in the `sdlhack` environment:

```bash
python -m analysis reduce --plate-map "OT protocols/examples/plate_map_round1.csv" \
  --reader analysis/examples/reader_round1_plate{1,2,3}.csv \
  --qc-reader analysis/examples/reader_round1_qc.csv --qc-map analysis/examples/qc_plate_map_round1.csv \
  --outdir runs/round1 --plots
python analysis/examples/make_toy_run.py --outdir runs/toy && python -m analysis qc --run runs/toy && python -m analysis report --run runs/toy
```
