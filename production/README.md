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
    - Results are uploaded here as the plate reader saves them, `.xlsx` workbooks; `run_bo.sh` converts each one to a
      `.csv` of the same name next to it (`production/convert_reader_xlsx.py`), so the folder ends up with both
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
| round N laid out, exports in `uvvis/` incomplete | stops (exit code 2) and lists the exact file names it is waiting for: the three plates and the solvent blank plate |
| round N exports in `uvvis/` | `analysis reduce` → `bo_bridge merge` → `SDL_BO suggest --branch` → `bo_bridge layout` for round N+1 into `ratios/`; then `analysis qc` into `csvs/figures/` and one `analysis report` per arm into `csvs/figures/phthalimide/` and `csvs/figures/others/` |
| round N+1 already laid out | nothing (re-run after the lab uploads round N+1) |

It never overwrites a finished round, so it is safe to re-run, and it exits with code 2 while it is still waiting for reader
files. `--seed N` changes the BO's random fallbacks, `--no-figures` skips the QC and report figures, `--allow-no-blank`
goes on without `reader_roundN_solvents.xlsx` (only if the blank plate really was not read: nothing is then subtracted,
and in round 0 the wavelengths every later round reuses are picked on raw spectra).

Rounds are final once merged: a reader file corrected after `results_roundN_wells.csv` exists is converted but not
re-analysed. To redo round N, delete `results_roundN_wells.csv` and the round N+1 files in `ratios/` (if the lab has not
run them yet) and re-run.

**What the lab uploads to `csvs/uvvis/`** (names matter; N = round, plates 0, 1, 2). Save the reader's workbooks as
`.xlsx` under these names; `run_bo.sh` turns each `reader_roundN_*.xlsx` into the `.csv` the analysis reads (a `.csv` at
least as new as its `.xlsx` is kept, so a hand-made `.csv` also works).

**Reader workbook format** (Tecan Infinite 200 PRO, i-control export; checked against the lab's example
`Absorbancescan.xlsx`, which is kept out of git). **One plate per workbook**, one scan sheet in it (an empty extra sheet
is fine; a workbook with several scan sheets is refused with their names, so copy each scan into its own file). On that sheet:

| Rows | Content | Used? |
|---|---|---|
| 1-28 | instrument, date, plate type, and the scan settings (`Wavelength Start`, `End`, `Step Size`, `Part of Plate`, temperature) | no |
| 29 | `Wavel.` then the wavelengths across (230, 234, ... as numbers) | yes |
| 30 on | one row per well: the well name (`A1`, `A2`, ...) then one absorbance per wavelength | yes |
| after | blank rows and `End Time:` | no |

Absorbances are plain numbers; an over-range reading is the text `OVER` (`>4` is accepted too) and is read as absorbance
4.0, so that wavelength counts as opaque and the well is flagged saturated. Any other text stops the conversion with the
well names. The block is found wherever it sits, also transposed (wells across, wavelengths down). Any wavelength range and
step is read, and the plates and the blank plate may differ: `reduce` interpolates them onto plate 0's wavelengths over
the range they all cover. Every plate-map well must be in the scan (`Part of Plate` A1-H12 for the sample plates; at
least this round's column for the blank plate).

| File | Content |
|---|---|
| `reader_roundN_plate0.xlsx`, `..._plate1.xlsx`, `..._plate2.xlsx` | reader workbook (format above) of each sample plate, all 96 wells. Planned scan: 200-700 nm in 5 nm steps. A `.csv` of the same name is read instead if it is newer: a long table `well, wavelength_nm, absorbance`, or one row per well under a `Wavel.` header (`,`, or `;` with decimal commas) |
| `reader_roundN_solvents.xlsx` | plate-reader export of the solvent blank plate (OT-2 slot 6, kept for the whole campaign), same format. The robot fills one column per round, one well per solvent: round 0 **A1 DMF, B1 acetone, C1 EtOH, D1 iPrOH, E1 water, F1 iPrOAc, G1 tBuOAc**, round 1 A2-G2, round 2 A3-G3; the analysis reads round N's column N + 1, measured every round at the same delay and fill (300 µL) as the sample plates. Used to predict every sample well's blank. Required: `run_bo.sh` waits for it like the plate files (`--allow-no-blank` to go on without it, with nothing subtracted) |
| `plate_log_roundN.csv` (optional) | `plate,read_delay_min` with rows 0, 1, 2: minutes from end of shaking to the read |

**What the lab gets from `csvs/ratios/`:** `ot_input_roundN.csv` (3 identical sample plates) (the pure-solvent blank wells are a separate small set, see the upload table below). `plate_map_roundN.csv` says what is in every well. From round 1 on the phthalimide block and the other three blocks hold different conditions (one per arm), so read the plate map, not the round's condition list, for what is in a well.

Everything the analysis derives (`endpoint_roundN_*.csv`, `wavelengths_roundN.csv`, `results_roundN_wells.csv`,
`bo_dataset.csv`, `bo_dataset_shared.csv`, `figures/`) lands in `csvs/` itself; `analysis qc` and `report` read the
whole `csvs/` tree (`report` runs once per arm, into `figures/phthalimide/` and `figures/others/`). **After round 0**, read `csvs/wavelengths_round0.csv`: its `measurable` column says which solutes
the UV readout can follow (see "Interpretation notes").

## What is in `config.toml` (as of 2026-10-20)

| Section | Values | Notes |
|---|---|---|
| `numbering` | first round 0, first plate 0, first mixture condition 1 | a condition is one solvent or one mixture; the DMF control is condition 0; well names stay A1–H12 |
| `well` | 300 µL per well, 5 µL minimum component, up to 3 solvents | the control well is 300 µL of pure DMF |
| `plates` | 3 identical plates per round; 25 mL trough fill, 1 mL dead volume; 2 reservoirs (slot 5 + the slot-4 backup) | no QC plate; the pure-solvent blank wells A1-G1 are read each round separately; the lab may load 30 mL per trough (Scientist instructions), the protocol plans with 25 mL; `limit_solvent_to_trough = false`: the BO is not held to one trough per solvent, so a round may need up to 48 mL from the two reservoirs, or above that a spare trough (`bo_bridge.py layout` warns; add it to `SOLVENT_TROUGHS` here and in the protocol) |
| `reference` | DMF | pure control in every solute block, never mixed |
| `arms` | phthalimide: Phthalimide; others: Glutarimide, Boc-hydroxyproline, Succinimide | after the shared round-0 seed design the campaign splits into these independent trajectories, each optimising the minimum over its solutes with its own GPs; every solute is in exactly one arm (`SDL_BO/README.md`, "Arms") |
| `solutes` | Glutarimide, Boc-hydroxyproline, Phthalimide, Succinimide | plate-block order; set `wavelength_nm` to the absorption maximum before round 0 (snapped to the nearest scanned wavelength; absent = picked from the raw DMF-control spectrum, which lands on DMF's UV edge) |
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
  as 1-23 (`R0_seed01`…). A1 is `round0_plate0_solute0_cond0` (naming convention given by the user, 2026-10-20). The
  per-well name is not yet written to any file; `condition_id` (`R0_seed01`) still identifies a mixture across solutes
  and plates.
- **UV readout concern and the conservative answer.** DMF is opaque below about 270 nm and acetone below about
  330 nm, while glutarimide, succinimide and Boc-hydroxyproline have little absorbance above about 250 nm; only
  phthalimide (about 295 nm) has a comfortable band. Since the plan cannot change once the campaign starts,
  `analysis reduce` was built to read every solute only inside the wavelength window where **every** solvent is
  transparent (blank below 1.0 absorbance) and to declare a solute **not measurable** when its DMF-control signal is
  within 3 x the noise (`wavelengths_roundN.csv`, column `measurable`; PLAN decision 15). That window needs solvent
  blanks: the round's column of pure-solvent wells (A1-G1 in round 0, A2-G2 in round 1, ...; `reader_roundN_solvents.csv`) gives them. Without that file the window
  is inactive, nothing is subtracted and the solvent's own absorbance stays in every well. **Set `wavelength_nm` for each solute in
  `config.toml` if the maxima are known**: left unset, round 0 picks each solute's wavelength from its blank-corrected DMF-control spectrum and every later round reuses it (`analysis reduce`), so no one has to intervene; without a solvent-blank file the peak is picked on the raw DMF-control spectrum and lands on DMF's own
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
