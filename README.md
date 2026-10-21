# SwissSigma-SDLhack

Self-driving-lab code for finding green-solvent mixtures that dissolve PROTAC-like building
blocks (proposal: `data/project_proposal/`). An Opentrons OT-2 builds solvent mixtures in
96-well plates, a UV-Vis plate reader measures absorbance as a solubility proxy, and Bayesian
optimisation (BO) picks the next round of mixtures. Each subfolder has its own README.

## Setup

```bash
bash setup.sh                         # macOS, Linux, Windows Git Bash: installs uv, Python 3.12 and every package, then checks
uv run pytest tests/                  # unit, interface and branched-campaign tests, ~30 s
uv run python examples/toy_additive_pipeline.py   # whole loop on fake additive chemistry, ~1 min/round; outputs kept in examples/toy_additive_output/
production/run_bo.sh production/csvs                  # the real campaign: one call per round, see production/README.md
```

## Folders

| Folder | What it holds |
|---|---|
| `production/` | **The real experiment's definition**: `config.toml` (solutes, solvents and their troughs, 300 µL wells, zero-based numbering) read by every module; `config.py` loads and validates it. Change the experiment here. `run_bo.sh production/csvs` runs one BO round from the lab's `production/csvs/` folder (round 0 is already in it) (robot files into `csvs/ratios/`, reader exports read from `csvs/uvvis/`). |
| `OT protocols/` | **Source of truth for the plate layout and all CSV formats.** OT-2 protocol `sdl_solubility_ot2.py` (one round = 3 identical plates), `bo_bridge.py` (suggestions → robot CSV + plate map; plate-reader exports → `bo_dataset.csv`), custom labware, deck/plate maps, `tools/check_all.py`. |
| `OTFlex analog/` | Same liquid handling replayed on a Flex, for timing a round before the real run. |
| `analysis/` | `python -m analysis reduce / qc / report`: plate-reader spectra → one absorbance per well per plate in the format `bo_bridge.py merge` takes, experiment-quality figures (`qc_summary.md`) and study-aim figures (`report_summary.md`). |
| `SDL_BO/` | Bayesian optimisation: `python -m SDL_BO init / suggest / report`. Reads `bo_dataset.csv`, writes `suggestions_roundN.csv`. |
| `tests/` | pytest suite: per-module tests plus interface tests that run the real `bo_bridge.py`. |
| `examples/` | `toy_additive_pipeline.py`: runs the whole loop with fake additive solubility and checks BO homes in on the best pure solvent. Its outputs (every CSV of every round, plus `analysis qc` / `report` figures and summaries in `figures/`) are tracked in `examples/toy_additive_output/` and `examples/toy_additive_output_one_plate/` as debugging material; `examples/toy_synergy_output/` is the matching run from `analysis/examples/make_toy_run.py` (see "Worked examples"). |
| `analysis/examples/` | Fake plate reader; synthetic round-0 exports (3 plates, optional blank) for the example plate map; `make_toy_run.py` builds a fake multi-round campaign folder for `analysis qc / report` without SDL_BO. |
| `data/Opentrons_Example_Files/` | Reference protocols and labware provided by the organisers (read-only). |
| `data/project_proposal/` | Project proposal (read-only). |

## The loop

```
python -m SDL_BO init                       ──► suggestions_round0.csv
python bo_bridge.py layout                  ──► ot_input_round0.csv (robot) + plate_map_round0.csv
OT-2 run (3 sample plates)                  ──► plate reader ──► reader_round0_plate{0,1,2}.csv
python -m analysis reduce                   ──► endpoint_round0_plate{0,1,2}.csv (one absorbance per well)
python bo_bridge.py merge                   ──► bo_dataset.csv
python -m SDL_BO suggest --branch           ──► suggestions_round1.csv (a solute column: one arm per solute group)   ... repeat
python -m analysis qc / report              ──► figures + qc_summary.md / report_summary.md (any time, all rounds so far)
```

Keep every round of a campaign in one folder: `analysis qc` and `report` find the rounds from the `plate_map_roundN.csv` files there.

## Worked examples

Three complete fake campaigns are tracked in the repo, with every intermediate file and the analysis outputs. The first
two come from `examples/toy_additive_pipeline.py` (real SDL_BO, additive chemistry in which DMC is the best solvent for
every solute); the third from `analysis/examples/make_toy_run.py` (random seeded suggestions, no SDL_BO, synergistic
chemistry that rewards balanced mixtures, and plate logs, band heights chosen so Boc-hydroxyproline saturates and
Succinimide sits near the noise; its solutes are the production ones, the two additive runs predate the config and use S1-S4):

| Folder | Rounds × plates | Look at |
|---|---|---|
| `examples/toy_additive_output/` | 3 × 3 | `figures/qc_summary.md` (Q1, Q2, Q4–Q6 with figures), `figures/report_summary.md` (R1–R7 with figures) |
| `examples/toy_additive_output_one_plate/` | 2 × 1 | the same, showing what the checks do without replicate plates; with 3× the solvent budget per round the exploit picks themselves become DMC-rich (mean DMC fraction 0.96 vs 0.30 in the 3-plate run, where the 25 mL DMC trough runs out before the picks can get richer; both runs were made with the old per-round solvent cap, which production has since turned off) |
| `examples/toy_synergy_output/` | 3 × 3 | the contrasting case: the best mixture is a ternary that beats every single solvent (R2, z = 243), 177 of 180 synergies are significant (R5), the GP landscape shows an interior optimum (R4); Q4 flags the saturated Boc-hydroxyproline controls and the acetone wells read for glutarimide |

Each folder holds, per round, `suggestions_roundN.csv` → `ot_input_roundN.csv` + `plate_map_roundN.csv` →
`reader_roundN_plate{P}.csv` (+ blank) → `endpoint_roundN_plate{P}.csv` + `wavelengths_roundN.csv` →
`results_roundN_wells.csv`, plus the cumulative `bo_dataset.csv` and `bo_dataset_shared.csv` (and `report.txt` from
SDL_BO in the additive runs; `plate_log_roundN.csv` in the synergy
run). Regenerate the synergy run with
`python analysis/examples/make_toy_run.py --outdir examples/toy_synergy_output`, then rerun `python -m analysis qc` and
`report --run examples/toy_synergy_output` so the committed summaries stay in step.

## Experiment definition (from `production/config.toml`; layout from `bo_bridge.py`)

- **Solutes:** Glutarimide, Boc-hydroxyproline, Phthalimide, Succinimide (plate-block order).
- **Solvents:** acetone, EtOH, i-PrOH, water, i-PrOAc, t-BuOAc as mixture components (CSV names `acetone, EtOH, iPrOH, water, iPrOAc, tBuOAc`); DMF only as the pure reference control.
- **Plate layout:** 4 solutes × 24 wells each: 1 DMF control + 23 conditions, run on 3 identical plates per round. In round 0 the 23 conditions are shared by all solutes; from round 1 the phthalimide block and the other three blocks hold different conditions (one set per arm).
- **Mixtures:** 1-3 solvents, integer µL summing to 300 µL, each used solvent ≥ 5 µL. SDL_BO proposes in 5 µL steps. It does **not** limit a round to one trough per solvent (see "Solvent trough volume" below).
- **Forbidden pairs:** water with i-PrOAc and water with t-BuOAc are immiscible (`[[forbidden_pairs]]` in the config); SDL_BO and `bo_bridge.py grid` never propose them and `layout` refuses a suggestions row that contains one.
- **Numbering:** rounds and plates start at 0 (`round0`, `plate0`). A condition is one solvent or one mixture: the DMF control is condition 0 and the mixtures are conditions 1–23 (`R0_seed01`…), and every well on every plate has a sample id `round{R}_plate{P}_solute{S}_cond{C}` (naming convention given by the user; A1 of round 0, plate 1 is `round0_plate1_solute0_cond0`). `bo_bridge.py` writes it as `sample_id` in `results_roundN_wells.csv` (and its parts `solute_index`, `cond` in the plate map); `cond` is the well's position in its solute block, cond0 = the DMF control. `condition_id` (`R0_seed01`, `R1_others_exploit07`, …) still names the mixture; well names stay `A1`–`H12`.
- **Objective:** absorbance relative to the DMF control per solute. Round 0 is one shared design on all four solutes; from round 1 on the campaign splits into two independent arms (`[[arms]]` in the config): **phthalimide** alone, and the **minimum of glutarimide, Boc-hydroxyproline and succinimide**. Each arm has its own GPs trained on the seed round and its own wells, and its own plate blocks.

**Solvent trough volume (no cap, user decision 2026-10-20).** Each solvent has one trough on the 8-trough reservoir (organiser
labware, 30 mL nominal); the protocol fills it with 25 mL and keeps 1 mL as dead volume, so 24 mL per solvent. Every
condition is pipetted into 3 plates and each solute block it is in, so a round whose conditions together hold more than
about 1960 µL of one solvent (a mean fraction of 0.28 per well) needs more than one trough. SDL_BO no longer holds its
picks to that limit (`limit_solvent_to_trough = false` in `production/config.toml`; `true` restores it, with each solute
block owning a quarter of the trough). **Consequence:** `bo_bridge.py layout` prints a "TOO MUCH" fill sheet and a warning, and
the OT-2 protocol refuses to run (and simulate) until a spare trough for that solvent (e.g. the unused H1) is added to
`SOLVENT_TROUGHS` in the protocol and in the config and loaded. In the fake branched run, one solvent exceeded its trough in
round 3, by 1.9 mL.

## Pending decisions and open questions

Open before the first real round; the details and current placeholders live in the linked documents.

- **Analysis step** ([`analysis/PLAN.md`](analysis/PLAN.md), "Decisions for review"): real solute names and absorption
  maxima, the plate reader's linear range and export format, the plate-log format, adding solvent blanks back,
  and whether the figures also go into slides.
- **Robot run** ([`OT protocols/README.md`](OT%20protocols/README.md), "Before running" and "Known limitations"):
  polystyrene readout plates attacked by esters, ethers and DMF; the fill time is a simulator estimate until a water dry run.
- **Solvent trough volume** (see "Solvent trough volume" above): the BO is no longer capped, so a round may need a second trough for a favoured solvent (e.g. the unused H1) in the protocol and config; decide who adds it.
- **UV readout** ([`production/README.md`](production/README.md), "Interpretation notes"): glutarimide, succinimide and
  Boc-hydroxyproline absorb little UV above about 250 nm while DMF and acetone cut off at 270 and 330 nm, so the absorbance
  readout may not work for them. With no blanks run for now (to be added back later), nothing is subtracted, and
  `wavelength_nm` must be set per solute in `production/config.toml` before round 0 or the peak lands on DMF's own UV edge.
- **Protocol notes** (`data/261018_protocol/`, not yet in git): run naming convention and where plate-reader exports are stored.
