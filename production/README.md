# production

**The one place the real experiment is defined.** `config.toml` holds the solutes, solvents, reservoir troughs,
volumes and numbering convention for the production campaign; `config.py` reads and validates it and exposes the
values as constants for the rest of the repo. Change the experiment here, not in the modules.

```python
from production.config import SOLUTES, ALL_SOLVENTS, GREEN_SOLVENTS, REFERENCE_SOLVENT, SOLVENT_TROUGHS, \
    PLATE_ATTACKERS, TOTAL_UL, MIN_UL, N_PLATES, FIRST_ROUND, FIRST_PLATE, FIRST_CONDITION, ARMS, LIMIT_SOLVENT_TO_TROUGH
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
bash production/run_bo.sh production/csvs       # from anywhere, after  bash setup.sh  once; uses the repo's uv environment
```

The script looks at what is in `csvs/` and does the next thing:

| State of `csvs/` | What the script does |
|---|---|
| empty | round 0 seed design (`SDL_BO init`), robot files for round 0 into `ratios/` |
| round N laid out, no exports in `uvvis/` | stops and lists the exact file names it is waiting for |
| round N exports in `uvvis/` | `analysis reduce` → `bo_bridge merge` → `SDL_BO suggest --branch` → `bo_bridge layout` for round N+1 into `ratios/`; then `analysis qc` into `csvs/figures/` and one `analysis report` per arm into `csvs/figures/phthalimide/` and `csvs/figures/others/` |
| round N+1 already laid out | nothing (re-run after the lab uploads round N+1) |

It never overwrites a finished round, so it is safe to re-run, and it exits with code 2 while it is still waiting for reader
files. `--seed N` changes the BO's random fallbacks, `--no-figures` skips the QC and report figures.

**What the lab uploads to `csvs/uvvis/`** (names matter; N = round, plates 0, 1, 2):

| File | Content |
|---|---|
| `reader_roundN_plate0.csv`, `..._plate1.csv`, `..._plate2.csv` | plate-reader export of each sample plate, saved as is: the reader's own scan export (`Wavel.;300;310;…`, one row per well, `;` with decimal commas) or `well, wavelength_nm, absorbance` (full spectra preferred; fixed wavelengths work) |
| `plate_log_roundN.csv` (optional) | `plate,read_delay_min` with rows 0, 1, 2: minutes from end of shaking to the read |

**What the lab gets from `csvs/ratios/`:** `ot_input_roundN.csv` (3 identical sample plates) (no QC or blank plate is run for now). `plate_map_roundN.csv` says what is in every well. From round 1 on the phthalimide block and the other three blocks hold different conditions (one per arm), so read the plate map, not the round's condition list, for what is in a well.

Everything the analysis derives (`endpoint_roundN_*.csv`, `wavelengths_roundN.csv`, `results_roundN_wells.csv`,
`bo_dataset.csv`, `bo_dataset_shared.csv`, `figures/`) lands in `csvs/` itself; `analysis qc` and `report` read the
whole `csvs/` tree (`report` runs once per arm, into `figures/phthalimide/` and `figures/others/`). **After round 0**, read `csvs/wavelengths_round0.csv`: its `measurable` column says which solutes
the UV readout can follow (see "Interpretation notes").

## What is in `config.toml` (as of 2026-10-20)

| Section | Values | Notes |
|---|---|---|
| `numbering` | first round 0, first plate 0, first mixture condition 1 | a condition is one solvent or one mixture; the DMF control is condition 0; well names stay A1–H12 |
| `well` | 300 µL per well, 5 µL minimum component, up to 3 solvents | the control well is 300 µL of pure DMF |
| `plates` | 3 identical plates per round; 25 mL trough fill, 1 mL dead volume | no QC or blank plate for now; `limit_solvent_to_trough = false`: the BO is not held to one trough per solvent, so a round may need a spare trough (`bo_bridge.py layout` warns; add it to `SOLVENT_TROUGHS` here and in the protocol) |
| `reference` | DMF | pure control in every solute block, never mixed |
| `arms` | phthalimide: Phthalimide; others: Glutarimide, Boc-hydroxyproline, Succinimide | after the shared round-0 seed design the campaign splits into these independent trajectories, each optimising the minimum over its solutes with its own GPs; every solute is in exactly one arm (`SDL_BO/README.md`, "Arms") |
| `solutes` | Glutarimide, Boc-hydroxyproline, Phthalimide, Succinimide | plate-block order; set `wavelength_nm` to the absorption maximum before round 0 (absent = picked from the raw DMF-control spectrum, which lands on DMF's UV edge) |
| `solvents` | DMF (A1), acetone (B1), EtOH (C1), i-PrOH (D1), water (E1), i-PrOAc (F1), t-BuOAc (G1) | `name` without hyphens is the CSV identifier, `label` the display name; H1 stays the diluent |

`attacks_polystyrene` marks the solvents expected to craze the polystyrene readout plate (acetone and the esters). Only
the fake plate reader and toy runs read it now: the plate-attack check went with the QC plate.

## Forbidden solvent pairs

Water is immiscible with i-PrOAc and with t-BuOAc, so a well containing either pair would phase-separate and its
absorbance would mean nothing. The user therefore forbade these two pairs (2026-10-20); they are listed under
`[[forbidden_pairs]]` and exposed as `FORBIDDEN_PAIRS` and `is_allowed(solvent_names)`. A mixture is forbidden
when it contains **both** solvents of a pair at any fraction; ternaries such as water + EtOH + i-PrOAc are
forbidden too, water + EtOH + acetone is fine. This is enforced in three places:

| Where | Effect |
|---|---|
| `SDL_BO/space.py` | the search space never contains a forbidden mixture, so the BO cannot propose one |
| `OT protocols/bo_bridge.py` | the round-0 seed grid skips them, and `layout` refuses any suggestions file that contains one |
| `analysis/examples/make_toy_run.py` | random toy suggestions skip them |

To forbid another pair, add a `[[forbidden_pairs]]` entry; to allow water/ester again, delete the entries.

## Interpretation notes for the user to confirm

- "Each well: 300 µL of DMF" means **300 µL total liquid per well**, with the reference control being 300 µL of
  pure DMF (confirmed by the user).
- Zero-based numbering applies to rounds, plates, solutes and conditions, not to well names. A condition is one solvent
  or one mixture of solvents; each solute block has conditions 0-23, with the DMF control as condition 0 and the mixtures
  as 1-23 (`R0_seed01`…). Every well on every plate is named `round{R}_plate{P}_solute{S}_cond{C}` (naming convention
  given by the user, 2026-10-20; `numbering.sample_id`): A1 of round 0, plate 1 is `round0_plate1_solute0_cond0`.
  `bo_bridge.py layout` writes `solute_index` and `cond` (position in the block, cond0 = DMF control) into the plate
  map and `merge` writes `sample_id` into `results_roundN_wells.csv`. `condition_id` still identifies a mixture across
  solutes and plates; its counter equals `cond` only in the round-0 seed design, because later rounds put re-tested
  mixtures first and name new picks per arm (`R1_others_exploit07`).
- **UV readout concern and the conservative answer.** DMF is opaque below about 270 nm and acetone below about
  330 nm, while glutarimide, succinimide and Boc-hydroxyproline have little absorbance above about 250 nm; only
  phthalimide (about 295 nm) has a comfortable band. Since the plan cannot change once the campaign starts,
  `analysis reduce` was built to read every solute only inside the wavelength window where **every** solvent is
  transparent (blank below 1.0 absorbance) and to declare a solute **not measurable** when its DMF-control signal is
  within 3 x the noise (`wavelengths_roundN.csv`, column `measurable`; PLAN decision 15). That window needs solvent
  blanks, and **no blanks are run for now** (user decision, 2026-10-20, to be revisited), so it is inactive:
  nothing is subtracted and the solvent's own absorbance stays in every well. **Set `wavelength_nm` for each solute in
  `config.toml` before round 0**: left unset, the peak is picked on the raw DMF-control spectrum and lands on DMF's own
  UV edge, saturated (`reduce` prints a warning). The `measurable` verdict still drops a solute from the worst-solute
  objective in `analysis report` and in SDL_BO's scoring.
- ~~Immiscible pairs~~: decided, see "Forbidden solvent pairs" above.

## Who reads it

| Consumer | What it takes |
|---|---|
| `OT protocols/bo_bridge.py` | solvents, solutes, troughs, the trough-cap switch, volumes, numbering (sdl_merge wiring) |
| `OT protocols/sdl_solubility_ot2.py` | `SOLVENT_TROUGHS` mirrored by hand; checked by `tests/` |
| `SDL_BO/` | solvents, number of solutes, volumes, arms, the optional trough cap, first round (sdl_merge wiring) |
| `analysis/` | reference solvent, first plate, arms (`report --arms`), solute wavelengths; the toy examples also read the polystyrene attackers |
| `tests/test_production_config.py` | that the file is consistent |
