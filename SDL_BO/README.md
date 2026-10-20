# SDL_BO

Bayesian optimisation for the green-solvent screen. **`bo_dataset.csv` in, suggestions CSV out.** It knows
nothing about the robot or the plate reader: `OT protocols/bo_bridge.py` owns every file format, and SDL_BO
reads and writes exactly those. The dataset file is the only state.

## Install

Use the repo environment (`mamba env create -f environment.yml`, `mamba activate sdlhack`). Run from the
repo root: `python -m SDL_BO ...` or `import SDL_BO`.

## The loop

```
python -m SDL_BO init                 ──► suggestions_round0.csv
python bo_bridge.py layout            ──► ot_input_round0.csv + plate_map_round0.csv
OT-2 run, plate reader, analysis      ──► one absorbance per well per plate
python bo_bridge.py merge             ──► bo_dataset.csv
python -m SDL_BO suggest              ──► suggestions_round2.csv   ... repeat layout / run / merge / suggest
```

```bash
python -m SDL_BO init    --out runs/suggestions_round0.csv
python -m SDL_BO suggest --dataset runs/bo_dataset.csv --out runs/suggestions_round1.csv
python -m SDL_BO report  --dataset runs/bo_dataset.csv
```

| Command | What it does |
|---|---|
| `init [--out FILE] [--force]` | First-round (round 0) design: the 6 pure green solvents + 17 space-filling mixtures. Refuses to overwrite without `--force`. |
| `suggest --dataset FILE [--out FILE] [--seed N]` | Next round from the dataset: 3 re-tests + 12 exploit + 8 explore. Default output `suggestions_round<N>.csv`. |
| `report --dataset FILE` | Best mixture, best pure solvent, Pareto front. |

`bo_bridge.py grid` is an alternative first-round design (random balanced binaries/ternaries); `init` picks maximin-spread mixtures instead.

## Formats (all defined by bo_bridge.py; names, volumes and numbering come from `production/config.toml`)

**Output, `suggestions_roundN.csv`**: one row per condition, run on every solute (no `solute` column).

```csv
condition_id,frac_acetone,frac_EtOH,frac_iPrOH,frac_water,frac_iPrOAc,frac_tBuOAc
R1_exploit00,0.2833,0.0,0.35,0.0,0.3667,0.0
```

- 23 rows per round = conditions per solute in bo_bridge's default layout (4 solutes × 24 wells, 1 DMF control each). bo_bridge adds the DMF control itself, so SDL_BO never writes DMF.
- Fractions are multiples of 5 µL of 300 µL, so bo_bridge dispenses them unchanged (its minimum is 5 µL).
- Per round, the conditions use at most 1960 µL of any one solvent in a single well set, so 3 plates × 4 solutes fit one 25 mL trough (24 mL usable, 2 % margin). Re-tests, exploit and explore picks are chosen within this budget; if fewer fit, fewer rows are written (bo_bridge leaves wells empty).
- `condition_id`: `R<round>_seed00`, `R<round>_exploit00`, `R<round>_explore00` (rounds and counters start at 0, as in `production/config.toml`); a re-test keeps the id it was first run under.

**Input, `bo_dataset.csv`** (from `bo_bridge.py merge`): one row per round × solute × condition with `round, solute,
condition_id, is_reference, frac_<solvent>..., rel_mean, ...`. SDL_BO uses `rel_mean` (absorbance relative to the
round's DMF control for that solute) and drops `is_reference = 1` rows. Rows without `rel_mean` are dropped with a
warning. Malformed files (fractions not summing to 1, DMF in a mixture, non-integer µL, more than 3 solvents) are refused with the CSV line numbers.

## How results are scored

- **ratio_\<solute\>** = `rel_mean`, averaged over every condition row with the same composition (re-tests across rounds).
- **score** of a mixture = its worst solute's ratio. 1.0 means as good as DMF for every solute. The optimizer maximizes it; a mixture that some solute never saw has no score.

## Use from Python

```python
from SDL_BO.campaign import seed_design, suggest_next_round
from SDL_BO.report import make_report

seed_design()                                         # DataFrame, round-0 suggestions
suggestions, info = suggest_next_round("bo_dataset.csv")  # info: round, kernels, cv_rmse, incumbent_score
print(make_report("bo_dataset.csv"))
```

`DatasetError` (a `ValueError`) is raised for bad data.

## Examples

`examples/make_examples.py` runs the real loop (SDL_BO → `bo_bridge.py layout` → fake plate reader from
`analysis/examples/fake_plate_reader.py` → `bo_bridge.py merge` → SDL_BO) for 3 rounds and leaves the files in
`examples/`: `suggestions_round0..3.csv`, `bo_dataset.csv`, `bo_dataset_shared.csv`. Invented data, not results.

## What is inside

| File | Role |
|---|---|
| `space.py` | Solvents, 5 µL grid (35,111 allowed mixtures), trough budget. Constants mirror `bo_bridge.py`. |
| `dataset.py` | Reads and validates `bo_dataset.csv`; per-mixture scores. |
| `model.py` | One Gaussian process per solute (kernel by cross-validation); exploit (batch expected improvement) and explore picks under a solvent `Budget`. |
| `campaign.py` | Round-1 design, `fit_per_solute` (GP per solute for plots), `suggest_next_round`. |
| `report.py` | Text report and Pareto front. |
| `cli.py`, `__main__.py` | Command line. |

To change the plate composition, edit `N_RETESTS`, `N_EXPLOIT`, `N_EXPLORE` in `campaign.py`. Solvents, volumes and
trough sizes must stay in step with `bo_bridge.py`.
