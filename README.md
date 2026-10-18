# SwissSigma-SDLhack
Code base for Opentrons protocols, BO, and data analysis


- `OT protocols/`: OT-2 protocol for the green-solvent solubility screen, the BO bridge
  (`bo_bridge.py`: robot CSV in, plate-reader results out), labware, maps and checks.
  Start with `OT protocols/README.md`.
- `BO instructions/`: Bayesian optimization (reads `bo_dataset.csv`, writes the next round's
  suggestions CSV)
- `data/`: Data folder containing subfolders for data outputs
    - `Opentrons_Example_Files`: Reference scripts provided
    - `runs/`: per-round robot CSVs, plate maps, plate-reader exports and the BO dataset
