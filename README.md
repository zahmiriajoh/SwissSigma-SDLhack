# SwissSigma-SDLhack

Self-driving-lab code for finding green-solvent mixtures that dissolve PROTAC-like building
blocks (proposal: `data/project_proposal/`). An Opentrons OT-2 builds solvent mixtures in
96-well plates, a UV-Vis plate reader measures absorbance as a solubility proxy, and Bayesian
optimisation (BO) picks the next round of mixtures. Each subfolder has its own README.

## Setup

```bash
mamba env create -f environment.yml   # Python 3.12, opentrons 8.8.2, numpy, pandas, scipy, scikit-learn, matplotlib, pytest
mamba activate sdlhack
pytest tests/                         # unit + interface tests, ~30 s
python examples/toy_additive_pipeline.py   # whole loop on fake additive chemistry, ~1 min/round; outputs kept in examples/toy_additive_output/
```

## Folders

| Folder | What it holds |
|---|---|
| `OT protocols/` | **Source of truth for the experiment and all CSV formats.** OT-2 protocol `sdl_solubility_ot2.py` (one round = 3 identical plates), `bo_bridge.py` (suggestions → robot CSV + plate map; plate-reader exports → `bo_dataset.csv`), custom labware, deck/plate maps, `tools/check_all.py`. |
| `OTFlex analog/` | Same liquid handling replayed on a Flex, for timing a round before the real run. |
| `analysis/` | `python -m analysis qc-layout / reduce / qc / report`: QC plate per round (blanks + calibration series), plate-reader spectra → one absorbance per well per plate in the format `bo_bridge.py merge` takes, experiment-quality figures (`qc_summary.md`) and study-aim figures (`report_summary.md`). |
| `SDL_BO/` | Bayesian optimisation: `python -m SDL_BO init / suggest / report`. Reads `bo_dataset.csv`, writes `suggestions_roundN.csv`. |
| `tests/` | pytest suite: per-module tests plus interface tests that run the real `bo_bridge.py`. |
| `examples/` | `toy_additive_pipeline.py`: runs the whole loop with fake additive solubility and checks BO homes in on the best pure solvent. Its outputs (every CSV of every round, plus `analysis qc` / `report` figures and summaries in `figures/`) are tracked in `examples/toy_additive_output/` and `examples/toy_additive_output_one_plate/` as debugging material. |
| `analysis/examples/` | Fake plate reader; synthetic round-1 exports (3 plates, blank, QC plate) for the example plate map; `make_toy_run.py` builds a fake multi-round campaign folder for `analysis qc / report` without SDL_BO. |
| `data/Opentrons_Example_Files/` | Reference protocols and labware provided by the organisers (read-only). |
| `data/project_proposal/` | Project proposal (read-only). |

## The loop

```
python -m SDL_BO init                       ──► suggestions_round1.csv
python bo_bridge.py layout                  ──► ot_input_round1.csv (robot) + plate_map_round1.csv
python -m analysis qc-layout                ──► qc_plate_map_round1.csv + ot_input_round1_qc.csv (blanks + calibration)
OT-2 run (3 sample plates + 1 QC plate) ──► plate reader ──► reader_round1_plate{1,2,3}.csv + reader_round1_qc.csv
python -m analysis reduce                   ──► endpoint_round1_plate{1,2,3}.csv + endpoint_round1_blank.csv (one absorbance per well)
python bo_bridge.py merge                   ──► bo_dataset.csv
python -m SDL_BO suggest                    ──► suggestions_round2.csv   ... repeat
python -m analysis qc / report              ──► figures + qc_summary.md / report_summary.md (any time, all rounds so far)
```

Keep every round of a campaign in one folder: `analysis qc` and `report` find the rounds from the `plate_map_roundN.csv` files there.

## Experiment definition (from `bo_bridge.py`)

- **Solvents:** 2MeTHF, EtOAc, DMC, CPME, MeCN, iPrOAc as mixture components; DMF only as the pure reference control.
- **Plate layout:** 4 solutes (S1-S4) × 24 wells each: 1 DMF control + 23 shared conditions, run on 3 identical plates per round.
- **Mixtures:** 1-3 solvents, integer µL summing to 300 µL, each used solvent ≥ 5 µL. SDL_BO proposes in 5 µL steps and keeps each solvent's per-round total within one 25 mL trough.
- **Objective:** absorbance relative to the DMF control per solute; a mixture's score is its worst solute's ratio.

## Pending decisions and open questions

Open before the first real round; the details and current placeholders live in the linked documents.

- **Analysis step** ([`analysis/PLAN.md`](analysis/PLAN.md), "Decisions for review"): real solute names and absorption
  maxima, the plate reader's linear range and export format, the QC plate layout and loadings, the plate-log format,
  and whether the figures also go into slides.
- **Robot run** ([`OT protocols/README.md`](OT%20protocols/README.md), "Before running" and "Known limitations"):
  polystyrene readout plates attacked by esters, ethers and DMF; the fill time is a simulator estimate until a water dry run.
- **Protocol notes** (`data/261018_protocol/`, not yet in git): run naming convention and where plate-reader exports are stored.
