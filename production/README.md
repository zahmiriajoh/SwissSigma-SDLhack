# production

**The one place the real experiment is defined.** `config.toml` holds the solutes, solvents, reservoir troughs,
volumes and numbering convention for the production campaign; `config.py` reads and validates it and exposes the
values as constants for the rest of the repo. Change the experiment here, not in the modules.

```python
from production.config import SOLUTES, ALL_SOLVENTS, GREEN_SOLVENTS, REFERENCE_SOLVENT, SOLVENT_TROUGHS, \
    PLATE_ATTACKERS, TOTAL_UL, MIN_UL, N_PLATES, FIRST_ROUND, FIRST_PLATE, FIRST_CONDITION
```

Standard library only (`tomllib`, Python 3.11+), so `OT protocols/bo_bridge.py` can load it as well. The OT-2
protocol itself runs on the robot and cannot import the repo: its `SOLVENT_TROUGHS` must be edited by hand to match,
and the test suite checks that it does.

## Folder structure

0. Deck map and plate map
1. Protocol script for one round
  - Upload this to Opentron
  - This reads the seed file in `ratios/`.
2. BO script(s) 
3. `csvs/` folder - CSV files
  - `ratios/`: Input files for Opentron
    - Seed file (first round)
    - File for each subsequent round
  - `uvvis/`: Results from each round
    - Results are uploaded here as CSVs
4. Bash script that runs the BO and outputs the files for the next round of experiments in `ratios/`:
   **`run_bo.sh`**, see below.
5. Bash script to set up the environment needed to use this repo.

We expect to receive the `csvs/` folder from the lab at the end of the day.

## `run_bo.sh`: one call per round

```bash
production/run_bo.sh csvs            # from anywhere; activates the sdlhack environment if needed
```

The script looks at what is in `csvs/` and does the next thing:

| State of `csvs/` | What the script does |
|---|---|
| empty | round 0 seed design (`SDL_BO init`), robot files and QC plate for round 0 into `ratios/` |
| round N laid out, no exports in `uvvis/` | stops and lists the exact file names it is waiting for |
| round N exports in `uvvis/` | `analysis reduce` → `bo_bridge merge` → `SDL_BO suggest` → `bo_bridge layout` and `analysis qc-layout` for round N+1 into `ratios/`; then `analysis qc` and `report` into `csvs/figures/` |
| round N+1 already laid out | nothing (re-run after the lab uploads round N+1) |

It never overwrites a finished round, so it is safe to re-run. `--seed N` changes the BO's random fallbacks,
`--no-figures` skips the QC and report figures.

**What the lab uploads to `csvs/uvvis/`** (names matter; N = round, plates 0, 1, 2):

| File | Content |
|---|---|
| `reader_roundN_plate0.csv`, `..._plate1.csv`, `..._plate2.csv` | plate-reader export of each sample plate: `well, wavelength_nm, absorbance` (full spectra preferred; fixed wavelengths work) |
| `reader_roundN_qc.csv` | the same for the QC plate |
| `plate_log_roundN.csv` (optional) | `plate,read_delay_min` with rows 0, 1, 2 and `qc`: minutes from end of shaking to the read |

**What the lab gets from `csvs/ratios/`:** `ot_input_roundN.csv` (3 identical sample plates) and `ot_input_roundN_qc.csv`
(1 QC plate, run separately; weigh `loading × nominal mass` of each solute into its calibration wells as listed in
`qc_plate_map_roundN.csv`). `plate_map_roundN.csv` says what is in every well.

Everything the analysis derives (`endpoint_roundN_*.csv`, `wavelengths_roundN.csv`, `results_roundN_wells.csv`,
`bo_dataset.csv`, `bo_dataset_shared.csv`, `figures/`) lands in `csvs/` itself; `analysis qc` and `report` read the
whole `csvs/` tree. **After round 0**, read `csvs/wavelengths_round0.csv`: its `measurable` column says which solutes
the UV readout can follow (see "Interpretation notes").

## What is in `config.toml` (as of 2026-10-20)

| Section | Values | Notes |
|---|---|---|
| `numbering` | first round 0, first plate 0, first condition 0 | "numbering for everything starts from zero"; well names stay A1–H12 |
| `well` | 300 µL per well, 5 µL minimum component, up to 3 solvents | the control well is 300 µL of pure DMF |
| `plates` | 3 identical plates per round; 25 mL trough fill, 1 mL dead volume | plus one QC plate per round (`analysis qc-layout`) |
| `reference` | DMF | pure control in every solute block, never mixed |
| `solutes` | Glutarimide, Boc-hydroxyproline, Phthalimide, Succinimide | plate-block order; add `wavelength_nm` once the absorption maximum is known (absent = pick from data) |
| `solvents` | DMF (A1), acetone (B1), EtOH (C1), i-PrOH (D1), water (E1), i-PrOAc (F1), t-BuOAc (G1) | `name` without hyphens is the CSV identifier, `label` the display name; H1 stays the diluent |

`attacks_polystyrene` marks the solvents expected to craze the polystyrene readout plate (acetone and the esters);
`analysis qc` uses it for the plate-attack check.

## Forbidden solvent pairs

Water is immiscible with i-PrOAc and with t-BuOAc, so a well containing either pair would phase-separate and its
absorbance would mean nothing. The user therefore forbade these two pairs (2026-10-20); they are listed under
`[[forbidden_pairs]]` and exposed as `FORBIDDEN_PAIRS` and `is_allowed(solvent_names)`. A mixture is forbidden
when it contains **both** solvents of a pair at any fraction; ternaries such as water + EtOH + i-PrOAc are
forbidden too, water + EtOH + acetone is fine. This is enforced in four places:

| Where | Effect |
|---|---|
| `SDL_BO/space.py` | the search space never contains a forbidden mixture, so the BO cannot propose one |
| `OT protocols/bo_bridge.py` | the round-0 seed grid skips them, and `layout` refuses any suggestions file that contains one |
| `analysis/qc_layout.py` | the QC plate's mixture blanks skip them (89 of 96 wells are then used) |
| `analysis/examples/make_toy_run.py` | random toy suggestions skip them |

To forbid another pair, add a `[[forbidden_pairs]]` entry; to allow water/ester again, delete the entries.

## Interpretation notes for the user to confirm

- "Each well: 300 µL of DMF" means **300 µL total liquid per well**, with the reference control being 300 µL of
  pure DMF (confirmed by the user).
- Zero-based numbering applies to rounds, plates, replicates and condition counters (`round0`, `plate0`, `R0_seed00`),
  not to well names; each solute block starts with its DMF control as item 0, so A1 is the control of solute 0 and A2 is
  condition 0 (confirmed by the user).
- **UV readout concern and the conservative answer.** DMF is opaque below about 270 nm and acetone below about
  330 nm, while glutarimide, succinimide and Boc-hydroxyproline have little absorbance above about 250 nm; only
  phthalimide (about 295 nm) has a comfortable band. Since the plan cannot change once the campaign starts,
  `analysis reduce` reads every solute only inside the wavelength window where **every** solvent is transparent
  (blank below 1.0 absorbance), on the band's shoulder if its maximum is hidden, and declares a solute
  **not measurable** when its DMF-control signal there is within 3 x the noise (`wavelengths_roundN.csv`, column
  `measurable`; PLAN decision 15). A solute flagged in any round is dropped from the worst-solute objective both in
  `analysis report` and in SDL_BO's scoring (still measured, fitted and listed, just not scored), so noise cannot steer
  the campaign. Measurements therefore stay valid in every well, at the cost of sensitivity.
  **Before round 0, run one QC plate alone** (`analysis qc-layout`, then `reduce` on it): the wavelength report tells
  you which solutes the UV readout can follow at all, while there is still time to change solutes, readout or plate.
  Prefer full-spectrum exports; if the reader must use fixed wavelengths, take them from that QC-plate run.
- ~~Immiscible pairs~~: decided, see "Forbidden solvent pairs" above.

## Who reads it

| Consumer | What it takes |
|---|---|
| `OT protocols/bo_bridge.py` | solvents, solutes, troughs, volumes, numbering (sdl_merge wiring) |
| `OT protocols/sdl_solubility_ot2.py` | `SOLVENT_TROUGHS` mirrored by hand; checked by `tests/` |
| `SDL_BO/` | solvents, number of solutes, volumes, trough budget, first round (sdl_merge wiring) |
| `analysis/` | reference solvent, polystyrene attackers, solvent labels |
| `tests/test_production_config.py` | that the file is consistent |
