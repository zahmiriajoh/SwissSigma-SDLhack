# SwissSigma-SDLhack

Self-driving-lab code for finding green-solvent mixtures that dissolve PROTAC-like building
blocks (proposal: `data/project_proposal/`). An Opentrons OT-2 builds solvent mixtures in
96-well plates, a UV-Vis plate reader measures absorbance as a solubility proxy, and Bayesian
optimisation (BO) picks the next round of mixtures. Each subfolder has its own README.

## Setup

```bash
mamba env create -f environment.yml   # Python 3.12, opentrons 8.8.2, numpy, pandas, scipy, scikit-learn, matplotlib, pytest
mamba activate sdlhack
pytest tests/                         # unit + interface tests, ~15 s
```

## Folders

| Folder | What it holds |
|---|---|
| `OT protocols/` | **Source of truth for the experiment and all CSV formats.** OT-2 protocol `sdl_solubility_ot2.py` (one round = 3 identical plates), `bo_bridge.py` (suggestions → robot CSV + plate map; plate-reader exports → `bo_dataset.csv`), custom labware, deck/plate maps, `tools/check_all.py`. |
| `OTFlex analog/` | Same liquid handling replayed on a Flex, for timing a round before the real run. |
| `analysis/` | Plate-reader spectra → one absorbance per well per plate (`python -m analysis reduce`), in the format `bo_bridge.py merge` takes. |
| `SDL_BO/` | Bayesian optimisation: `python -m SDL_BO init / suggest / report`. Reads `bo_dataset.csv`, writes `suggestions_roundN.csv`. |
| `tests/` | pytest suite: per-module tests plus interface tests that run the real `bo_bridge.py`. |
| `analysis/examples/` | Fake plate reader and synthetic full-spectrum exports (3 plates + blank) for the round-1 example plate map. |
| `data/Opentrons_Example_Files/` | Reference protocols and labware provided by the organisers (read-only). |
| `data/project_proposal/` | Project proposal (read-only). |

## The loop

```
python -m SDL_BO init                       ──► suggestions_round1.csv
python bo_bridge.py layout                  ──► ot_input_round1.csv (robot) + plate_map_round1.csv
OT-2 run (3 identical plates) ──► plate reader ──► reader_round1_plate{1,2,3}.csv (+ blank)
python -m analysis reduce                   ──► endpoint_round1_plate{1,2,3}.csv (one absorbance per well)
python bo_bridge.py merge                   ──► bo_dataset.csv
python -m SDL_BO suggest                    ──► suggestions_round2.csv   ... repeat
```

## Experiment definition (from `bo_bridge.py`)

- **Solvents:** 2MeTHF, EtOAc, DMC, CPME, MeCN, iPrOAc as mixture components; DMF only as the pure reference control.
- **Plate layout:** 4 solutes (S1-S4) × 24 wells each: 1 DMF control + 23 shared conditions, run on 3 identical plates per round.
- **Mixtures:** 1-3 solvents, integer µL summing to 300 µL, each used solvent ≥ 5 µL. SDL_BO proposes in 5 µL steps and keeps each solvent's per-round total within one 25 mL trough.
- **Objective:** absorbance relative to the DMF control per solute; a mixture's score is its worst solute's ratio.
