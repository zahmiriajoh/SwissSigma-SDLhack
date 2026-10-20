# SDL_BO

**History CSV in, candidates CSV out.** `SDL_BO` knows nothing about the robot or plate reader and keeps no state between calls: the history file is the only state.

## Install

`SDL_BO/` is self-contained (it imports nothing from outside itself). It needs Python 3.12+ and `numpy`, `pandas`, `scikit-learn` and `scipy`. Put the folder's parent directory on the path (or run from there) and use `python -m SDL_BO ...` or `import SDL_BO`.

## The loop

```
init ──► candidates.csv ──► run in lab, read plates ──► measured_wells.csv
                                                              │
        suggest ◄── history.csv ◄── merge ◄───────────────────┘
          │
          └──► candidates.csv (next round) ──► ... repeat
```

```bash
python -m SDL_BO init    --out candidates.csv                                    # 1. round-1 design
python -m SDL_BO merge   --round-data measured_wells.csv --history history.csv   # 2. add measured round
python -m SDL_BO suggest --history history.csv --out candidates.csv              # 3. next round's design
python -m SDL_BO report  --history history.csv                                   # summary, any time
```

Repeat steps 2 and 3 for every round. Turning the instrument output into `measured_wells.csv` is **your** step; `SDL_BO` does not do it.

| Command | What it does |
|---|---|
| `init [--out FILE] [--force]` | Writes the round-1 design. Refuses to overwrite `--out` without `--force`. |
| `merge --round-data FILE [--history FILE]` | Appends one round's wells to the history (created if absent). Refuses a round already present, and writes nothing on any error. |
| `suggest [--history FILE] [--out FILE] [--seed N]` | Designs the next round from the history. Overwrites `--out`. `--seed` makes the random fallbacks reproducible. |
| `report [--history FILE]` | Prints the best mixture, best single solvent and the Pareto front. |

Defaults: `--out candidates.csv`, `--history history.csv`, `--seed 0`. Errors print as one line starting `error:`.

## Input: `measured_wells.csv` (one round) and `history.csv` (all rounds)

One row per measured **well**; a design run in triplicate is 3 rows. The history is these files stacked.

| Column | Meaning |
|---|---|
| `round` | Positive whole number: 1, 2, 3, ... |
| `DMF`, `acetone`, `EtOH`, `iPrOH`, `water`, `iPrOAc`, `tBuOAc` | Volume fractions of the well; each row sums to 1. |
| `abs_<solute>` | One column per solute (any name after `abs_`): the absorbance reading. |

Extra columns (well position, replicate number, ...) are allowed and ignored.

```csv
round,DMF,acetone,EtOH,iPrOH,water,iPrOAc,tBuOAc,replicate,abs_proxy1,abs_proxy2
1,1.0,0.0,0.0,0.0,0.0,0.0,0.0,1,1.52,1.31
1,0.0,0.0,0.25,0.0,0.75,0.0,0.0,1,0.88,0.79
```

Rules (a breach is refused with an explanatory message and the CSV line number):
- **Every round needs its own pure-DMF control wells** (`DMF = 1`), and they must read above zero. Each plate is divided by its own control.
- DMF only ever appears as a pure control, never mixed.
- Fractions are multiples of 2.5% (1/40), with at most 3 solvents per mixture.
- Every solute column is numeric and finite. Wells with a missing reading are dropped for all solutes, with a warning. Negative absorbances are set to 0, with a warning.
- Do not use the names `score`, `is_dmf_control`, `mixture_key` or anything starting `ratio_` as columns.
- `merge` takes exactly one round per file and the same `abs_` columns as the existing history.

## Output: `candidates.csv`

32 designs to run, one per row: `round`, the 7 solvent fractions to dispense, and `type`.

```csv
round,DMF,acetone,EtOH,iPrOH,water,iPrOAc,tBuOAc,type
2,0.0,0.5,0.075,0.425,0.0,0.0,0.0,bo_exploit
```

| `type` | Count | Meaning |
|---|---|---|
| `seed` | 31 (round 1 only) | The 6 pure green solvents plus 25 well-spread mixtures. |
| `bo_exploit` | 16 | Untested mixtures most likely to beat the best score so far. |
| `bo_explore` | 10 | Untested mixtures the models are least sure about. |
| `retest` | 5 | Repeats of the 5 highest-scoring mixtures so far. |
| `reference` | 1 | Pure DMF control (`DMF = 1`). |

Round 1 has no `bo_*` or `retest` rows. Measuring each design in triplicate (96 wells per plate, one plate per solute) is the intended design; `SDL_BO` accepts any number of wells per design.

## How results are scored

- **ratio** = a well's absorbance / the mean DMF-control absorbance of the same round. 1.0 means as good as DMF.
- **score** of a mixture = its worst solute's ratio, after averaging each solute's ratio over the mixture's wells. The optimizer maximizes it.

## Use from Python

```python
from SDL_BO.campaign import seed_design, suggest_next_round
from SDL_BO.merge import append_round_to_history
from SDL_BO.report import make_report

candidates = seed_design()                                    # DataFrame, round 1
measured_wells = run_and_measure(candidates)                  # YOUR code: DataFrame in history format
append_round_to_history("history.csv", measured_wells)        # returns the combined history DataFrame
candidates, info = suggest_next_round("history.csv")          # (DataFrame, dict)
print(make_report("history.csv"))                             # str
```

| Function | Returns |
|---|---|
| `seed_design()` | Round-1 candidates DataFrame. |
| `append_round_to_history(history_path, round_rows)` | The combined history DataFrame; raises `MergeError` and writes nothing if the round is unusable. |
| `suggest_next_round(history_path, n_exploit=16, n_explore=10, n_retests=5, seed=0)` | `(candidates, info)`; `info` has `round`, `kernels` and `cv_rmse` (both keyed by solute) and `n_training_wells`. |
| `make_report(history_path)` | Text summary. |

`HistoryError` and `MergeError` (both `ValueError` subclasses) are raised for bad data.

## Try it on the example files

`examples/` holds invented data (not real results), run from the folder that contains `SDL_BO/`:

```bash
python -m SDL_BO merge   --round-data SDL_BO/examples/example_round1_measured_wells.csv --history history.csv
python -m SDL_BO suggest --history SDL_BO/examples/example_history.csv --out next_candidates.csv
python -m SDL_BO report  --history SDL_BO/examples/example_history.csv
```

| File | What it is |
|---|---|
| `example_round1_candidates.csv` | Output of `init`: the round-1 design (what to run). |
| `example_round1_measured_wells.csv` | Round 1 as measured: 96 wells, 4 solutes (what `merge` takes). |
| `example_history.csv` | A 4-round history (what `suggest` and `report` read). |

## What is inside

| File | Role |
|---|---|
| `space.py` | Solvents, the 2.5% grid and all 15,411 allowed mixtures. |
| `history.py` | Reads and validates the history; per-plate DMF normalization; per-well and per-mixture scores. |
| `merge.py` | Safe, atomic append of one round to the history file. |
| `model.py` | One Gaussian process per solute with cross-validated kernel choice; exploit (batch expected improvement) and explore picking. |
| `campaign.py` | Round-1 design and `suggest_next_round`. |
| `report.py` | Text report and Pareto front. |
| `cli.py`, `__main__.py` | Command line. |
| `examples/` | Invented example input and output files. |

To change the solvent list, grid, or plate composition, edit the constants in `space.py` (`ALL_SOLVENTS`, `GRID_STEPS`, `MAX_SOLVENTS_PER_MIXTURE`) and `campaign.py` (`N_RETESTS`, `N_EXPLOIT`, `N_EXPLORE`). Fix them before recording data: changing the grid afterwards makes an existing history invalid.

