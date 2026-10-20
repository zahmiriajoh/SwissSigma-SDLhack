# analysis/examples

Synthetic plate-reader data for developing and testing the analysis step (spectra → per-well
absorbance → `bo_bridge.py merge`). Everything here is fake and follows the formats of
`OT protocols/bo_bridge.py`.

## Files

- `fake_plate_reader.py`: the fake chemistry and export writers. Solvent and solute names are bo_bridge's (DMF, 2MeTHF, EtOAc, DMC, CPME, MeCN, iPrOAc; solutes S1-S4). Also imported by `SDL_BO/examples/make_examples.py` and `tests/`.
- `make_example_plates.py`: regenerates the exports below from the round-1 example plate map in `OT protocols/examples/plate_map_round1.csv` (4 solutes × 24 wells, 1 DMF control + 23 conditions each).
- `reader_round1_plate{1,2,3}.csv`: full-spectrum exports of the 3 identical plates of round 1. Long table with columns `well`, `wavelength_nm` (200-800 nm, 1 nm step), `absorbance`.
- `reader_round1_blank.csv`: the same plate without solids (solvent background only), for `bo_bridge.py merge --blank`.

## Fake chemistry

Each solute has one Gaussian band (S1 275 nm, S2 320 nm, S3 350 nm, S4 410 nm) on a UV-rising baseline with noise. Band height = 1.2 × a "dissolved fraction" = fraction-weighted per-solvent dissolving power plus a synergy bonus for balanced mixtures, capped at 1. DMF gives full dissolution.

## Running the analysis on these files

From the repo root in the `sdlhack` environment (see `../README.md` for the options):

```bash
python -m analysis reduce --plate-map "OT protocols/examples/plate_map_round1.csv" \
  --reader analysis/examples/reader_round1_plate{1,2,3}.csv \
  --blank analysis/examples/reader_round1_blank.csv --outdir runs/round1 --plots
```

This picks 275, 319, 349 and 410 nm for S1-S4 and writes the endpoint files that
`bo_bridge.py merge --reader ... --blank ...` reads. `bo_bridge.py merge` can also read the
long tables directly if `SOLUTE_WAVELENGTH_NM` is set in `bo_bridge.py`, but the analysis step
is the intended route.
