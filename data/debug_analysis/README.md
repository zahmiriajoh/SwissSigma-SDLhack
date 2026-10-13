# debug_analysis README

- Debug files to help with coding the final analysis of opentron outputs
- `make_example_uvvis.py`: generates synthetic UV-Vis plate-reader CSVs
- `example_uvvis_plate{1,2}.csv`: one file per 96-well plate. Index `wavelength_nm` (200-800 nm, 1 nm step); one absorbance column per well (`A1`..`H12`, row-major)
