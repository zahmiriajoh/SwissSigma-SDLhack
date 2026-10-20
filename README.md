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
| `production/` | **The real experiment's definition**: `config.toml` (solutes, solvents and their troughs, 300 µL wells, zero-based numbering) read by every module; `config.py` loads and validates it. Change the experiment here. |
| `OT protocols/` | **Source of truth for the plate layout and all CSV formats.** OT-2 protocol `sdl_solubility_ot2.py` (one round = 3 identical plates), `bo_bridge.py` (suggestions → robot CSV + plate map; plate-reader exports → `bo_dataset.csv`), custom labware, deck/plate maps, `tools/check_all.py`. |
| `OTFlex analog/` | Same liquid handling replayed on a Flex, for timing a round before the real run. |
| `analysis/` | `python -m analysis qc-layout / reduce / qc / report`: QC plate per round (blanks + calibration series), plate-reader spectra → one absorbance per well per plate in the format `bo_bridge.py merge` takes, experiment-quality figures (`qc_summary.md`) and study-aim figures (`report_summary.md`). |
| `SDL_BO/` | Bayesian optimisation: `python -m SDL_BO init / suggest / report`. Reads `bo_dataset.csv`, writes `suggestions_roundN.csv`. |
| `tests/` | pytest suite: per-module tests plus interface tests that run the real `bo_bridge.py`. |
| `examples/` | `toy_additive_pipeline.py`: runs the whole loop with fake additive solubility and checks BO homes in on the best pure solvent. Its outputs (every CSV of every round, plus `analysis qc` / `report` figures and summaries in `figures/`) are tracked in `examples/toy_additive_output/` and `examples/toy_additive_output_one_plate/` as debugging material; `examples/toy_synergy_output/` is the matching run from `analysis/examples/make_toy_run.py` (see "Worked examples"). |
| `analysis/examples/` | Fake plate reader; synthetic round-1 exports (3 plates, blank, QC plate) for the example plate map; `make_toy_run.py` builds a fake multi-round campaign folder for `analysis qc / report` without SDL_BO. |
| `data/Opentrons_Example_Files/` | Reference protocols and labware provided by the organisers (read-only). |
| `data/project_proposal/` | Project proposal (read-only). |

## The loop

```
python -m SDL_BO init                       ──► suggestions_round0.csv
python bo_bridge.py layout                  ──► ot_input_round0.csv (robot) + plate_map_round0.csv
python -m analysis qc-layout                ──► qc_plate_map_round0.csv + ot_input_round0_qc.csv (blanks + calibration)
OT-2 run (3 sample plates + 1 QC plate) ──► plate reader ──► reader_round0_plate{0,1,2}.csv + reader_round0_qc.csv
python -m analysis reduce                   ──► endpoint_round0_plate{0,1,2}.csv + endpoint_round0_blank.csv (one absorbance per well)
python bo_bridge.py merge                   ──► bo_dataset.csv
python -m SDL_BO suggest                    ──► suggestions_round1.csv   ... repeat
python -m analysis qc / report              ──► figures + qc_summary.md / report_summary.md (any time, all rounds so far)
```

Keep every round of a campaign in one folder: `analysis qc` and `report` find the rounds from the `plate_map_roundN.csv` files there.

## Worked examples

Three complete fake campaigns are tracked in the repo, with every intermediate file and the analysis outputs. The first
two come from `examples/toy_additive_pipeline.py` (real SDL_BO, additive chemistry in which DMC is the best solvent for
every solute); the third from `analysis/examples/make_toy_run.py` (random seeded suggestions, no SDL_BO, synergistic
chemistry that rewards balanced mixtures, QC plates and plate logs, band heights chosen so S1 saturates and S4 sits near
the noise):

| Folder | Rounds × plates | Look at |
|---|---|---|
| `examples/toy_additive_output/` | 3 × 3 | `figures/qc_summary.md` (Q1–Q7 with figures), `figures/report_summary.md` (R1–R7 with figures) |
| `examples/toy_additive_output_one_plate/` | 2 × 1 | the same, showing what the checks do without replicate plates; with 3× the solvent budget per round the exploit picks themselves become DMC-rich (mean DMC fraction 0.96 vs 0.30 in the 3-plate run, where the 25 mL DMC trough runs out before the picks can get richer) |
| `examples/toy_synergy_output/` | 3 × 3 (+ QC plate) | the contrasting case: a ternary beats every single solvent (R2, z = 4.9), every synergy is significant (R5), the GP landscape shows an interior optimum (R4); Q7 calibration and the Q3 read-delay and additivity panels have data; Q4 flags the saturated S1 controls |

Each folder holds, per round, `suggestions_roundN.csv` → `ot_input_roundN.csv` + `plate_map_roundN.csv` →
`reader_roundN_plate{P}.csv` (+ blank) → `endpoint_roundN_plate{P}.csv` + `wavelengths_roundN.csv` →
`results_roundN_wells.csv`, plus the cumulative `bo_dataset.csv` and `bo_dataset_shared.csv` (and `report.txt` from
SDL_BO in the additive runs; `qc_plate_map_roundN.csv`, `reader_roundN_qc.csv` and `plate_log_roundN.csv` in the synergy
run). The additive runs predate the QC plate, so their Q7 calibration section is empty. Regenerate the synergy run with
`python analysis/examples/make_toy_run.py --outdir examples/toy_synergy_output`, then rerun `python -m analysis qc` and
`report --run examples/toy_synergy_output` so the committed summaries stay in step.

## Experiment definition (from `production/config.toml`; layout from `bo_bridge.py`)

- **Solutes:** Glutarimide, Boc-hydroxyproline, Phthalimide, Succinimide (plate-block order).
- **Solvents:** acetone, EtOH, i-PrOH, water, i-PrOAc, t-BuOAc as mixture components (CSV names `acetone, EtOH, iPrOH, water, iPrOAc, tBuOAc`); DMF only as the pure reference control.
- **Plate layout:** 4 solutes × 24 wells each: 1 DMF control + 23 shared conditions, run on 3 identical plates per round.
- **Mixtures:** 1-3 solvents, integer µL summing to 300 µL, each used solvent ≥ 5 µL. SDL_BO proposes in 5 µL steps and keeps each solvent's per-round total within one 25 mL trough.
- **Numbering:** rounds, plates and condition counters start at 0 (`round0`, `plate0`, `R0_seed00`); well names stay `A1`–`H12`.
- **Objective:** absorbance relative to the DMF control per solute; a mixture's score is its worst solute's ratio.

**How the trough volume constrains BO.** Each solvent has one trough on the 8-trough reservoir (organiser labware, 30 mL
nominal); the protocol fills it with 25 mL and keeps 1 mL as dead volume, so 24 mL per solvent per round. Every condition
is pipetted 4 solutes × 3 plates = 12 times, so the 23 conditions of a round can together use at most about 1960 µL of
any one solvent, a mean fraction of 0.28 per well. BO cannot therefore fill a round with mixtures rich in one solvent,
even when it already knows that solvent is best: in the 3-plate toy run the picks average 0.30 DMC while the one-plate run,
with the same trough serving 4 wells per condition, reaches 0.96. The 25 mL fill and the one-trough-per-solvent assignment
are draft choices (`trough_fill_ul` and the trough list in `production/config.toml`), not scientific decisions; the
protocol allows a solvent to use more than one trough, and H1 (diluent) is currently unused.

## Pending decisions and open questions

Open before the first real round; the details and current placeholders live in the linked documents.

- **Analysis step** ([`analysis/PLAN.md`](analysis/PLAN.md), "Decisions for review"): real solute names and absorption
  maxima, the plate reader's linear range and export format, the QC plate layout and loadings, the plate-log format,
  and whether the figures also go into slides.
- **Robot run** ([`OT protocols/README.md`](OT%20protocols/README.md), "Before running" and "Known limitations"):
  polystyrene readout plates attacked by esters, ethers and DMF; the fill time is a simulator estimate until a water dry run.
- **Solvent trough volume** (see "How the trough volume constrains BO" above): give the solvent BO favours a second trough, e.g. the unused H1, or accept that no round can lean heavily on one solvent.
- **Solvent set** ([`production/README.md`](production/README.md), "Interpretation notes"): water is immiscible with i-PrOAc and
  t-BuOAc, so the grid proposes water/ester mixtures that will phase-separate unless those pairs are forbidden; glutarimide,
  succinimide and Boc-hydroxyproline absorb little UV above about 250 nm while DMF and acetone cut off at 270 and 330 nm,
  so the absorbance readout may not work for them.
- **Protocol notes** (`data/261018_protocol/`, not yet in git): run naming convention and where plate-reader exports are stored.
