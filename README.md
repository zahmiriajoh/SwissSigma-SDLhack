# SwissSigma-SDLhack

Self-driving-lab code for finding green-solvent mixtures that dissolve PROTAC-like building
blocks (proposal: `data/project_proposal/`). An Opentrons robot builds solvent mixtures in
96-well plates, a UV-Vis plate reader measures absorbance as a solubility proxy, and Bayesian
optimisation (BO) picks the next round of mixtures. Each subfolder has its own README.

## Folders

| Folder | What it holds |
|---|---|
| `OT protocols/` | OT-2 protocol `sdl_solubility_ot2.py` (one round = up to 3 identical plates), `bo_bridge.py` (suggestions → robot CSV + plate map; plate-reader exports → `bo_dataset.csv`), custom labware, deck/plate maps, `tools/check_all.py`. |
| `OTFlex analog/` | Same liquid handling replayed on a Flex, for timing a round before the real run. |
| `SDL_BO/` | Standalone BO package: `python -m SDL_BO init / merge / suggest / report`. History CSV in, candidates CSV out; one Gaussian process per solute. |
| `data/debug_analysis/` | Synthetic plate maps and UV-Vis spectra (200-800 nm, one column per well) for developing the analysis code. |
| `data/Opentrons_Example_Files/` | Reference protocols and labware provided by the organisers (read-only). |
| `data/project_proposal/` | Project proposal (read-only). |

## The loop

```
BO suggestions ──► bo_bridge.py layout ──► robot CSV ──► OT-2 run ──► plate reader exports
       ▲                                                                       │
       └──── SDL_BO suggest ◄── history CSV ◄── analysis (to be written) ◄─────┘
```

The analysis step (plate-reader spectra → per-well absorbance → BO history) is the part
still being built on `main`.

## Open inconsistencies between the merged branches

These need a decision before the pieces can be chained together:

- **Solvent set.** `OT protocols` and `data/debug_analysis` use 2-MeTHF, EtOAc, DMC, CPME, MeCN, iPrOAc (as in the proposal). `SDL_BO` uses acetone, EtOH, iPrOH, water, iPrOAc, tBuOAc.
- **Plate layout.** `OT protocols`: 4 solutes per plate, 24 wells each (1 DMF control + 23 conditions), 3 identical plates. `SDL_BO`: one plate per solute, 32 designs in triplicate. `data/debug_analysis`: 3 proxies, 20 mixtures, pure-solvent, blank and calibration wells.
- **Composition grid.** `bo_bridge.py` snaps volumes to 5 µL of 300 µL. `SDL_BO` requires fractions on a 2.5 % grid.
- **CSV formats.** `bo_bridge.py merge` writes `bo_dataset.csv` (one row per solute × condition); `SDL_BO merge` expects one row per well with `abs_<solute>` columns. Plate-reader parsing in `bo_bridge.py` takes a long table or an 8×12 grid, not the wavelength × well matrix used in `data/debug_analysis`.
