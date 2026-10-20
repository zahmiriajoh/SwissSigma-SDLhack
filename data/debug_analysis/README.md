# debug_analysis README

Synthetic plate-reader data for developing the analysis step (spectra → per-well absorbance →
`bo_bridge.py merge`). Everything here is fake and follows the formats of `OT protocols/bo_bridge.py`.

## Files

- `fake_plate_reader.py`: the fake chemistry and export writers. Solvent and solute names are bo_bridge's (DMF, 2MeTHF, EtOAc, DMC, CPME, MeCN, iPrOAc; solutes S1-S4). Also imported by `SDL_BO/examples/make_examples.py`.
- `make_example_plates.py`: regenerates the exports below from the round-1 example plate map in `OT protocols/examples/plate_map_round1.csv` (4 solutes × 24 wells, 1 DMF control + 23 conditions each).
- `reader_round1_plate{1,2,3}.csv`: full-spectrum exports of the 3 identical plates of round 1. Long table with columns `well`, `wavelength_nm` (200-800 nm, 1 nm step), `absorbance`.
- `reader_round1_blank.csv`: the same plate without solids (solvent background only), for `bo_bridge.py merge --blank`.

## Fake chemistry

Each solute has one Gaussian band (S1 275 nm, S2 320 nm, S3 350 nm, S4 410 nm) on a UV-rising baseline with noise. Band height = 1.2 × a "dissolved fraction" = fraction-weighted per-solvent dissolving power plus a synergy bonus for balanced mixtures, capped at 1. DMF gives full dissolution.

## Feeding bo_bridge

`bo_bridge.py merge` reads these long tables directly. Because each solute needs its own wavelength, either set `SOLUTE_WAVELENGTH_NM` in `bo_bridge.py` (S1 275, S2 320, S3 350, S4 410 for these files) or first reduce each export to one absorbance per well (`well`, `absorbance`), which is the job of the analysis code:

```bash
python "OT protocols/bo_bridge.py" merge --plate-map "OT protocols/examples/plate_map_round1.csv" \
  --reader data/debug_analysis/reader_round1_plate{1,2,3}.csv --blank data/debug_analysis/reader_round1_blank.csv \
  --dataset bo_dataset.csv
```
