# analysis

**Plate-reader spectra in; endpoint files for `bo_bridge.py merge`, QC figures and the study report out.**
Three commands, all run from the repo root with `python -m analysis ...`:

| Command | In | Out |
|---|---|---|
| `reduce` | reader exports of the sample plates (optionally a solvent-only blank plate), plate map | one `(well, absorbance)` file per plate at each solute's wavelength, `wavelengths_roundN.csv` |
| `qc` | a campaign folder | experiment-quality figures Q1, Q2, Q4–Q6 and `qc_summary.md` |
| `report` | a campaign folder | study-aim figures R1–R7 and `report_summary.md` |

What each figure shows and the decisions behind them are in [`PLAN.md`](PLAN.md).

## Install

Part of the repo-wide uv environment (`bash setup.sh` at the repo root; run commands as `uv run python -m analysis ...`): Python 3.12,
`numpy`, `pandas`, `matplotlib`; `report` imports `SDL_BO` for the Gaussian-process landscape.

## One round

```
bo_bridge.py layout ──► plate_map_roundN.csv, ot_input_roundN.csv
OT-2: 3 sample plates (ot_input_roundN.csv)
plate reader ──► reader_roundN_plate{0,1,2}.csv                              lab ──► plate_log_roundN.csv (optional)
analysis reduce ──► endpoint_roundN_plate{0,1,2}.csv, wavelengths_roundN.csv
bo_bridge.py merge --reader endpoint_... ──► results_roundN_wells.csv, bo_dataset.csv
analysis qc / report (any time, all rounds so far)
```

```bash
python -m analysis reduce --plate-map runs/prod/plate_map_round0.csv --reader runs/prod/reader_round0_plate{0,1,2}.csv --plots
python "OT protocols/bo_bridge.py" merge --plate-map runs/prod/plate_map_round0.csv \
    --reader runs/prod/endpoint_round0_plate{0,1,2}.csv --dataset runs/prod/bo_dataset.csv
python -m analysis qc --run runs/prod
python -m analysis report --run runs/prod          # add --arms for a branched campaign: one report per arm
```

Keep every round of a campaign in **one folder** (the `--outdir` of `layout`, `reduce` and `merge`): `qc` and `report`
find the rounds from the `plate_map_roundN.csv` files there and write to `<folder>/figures/`. The production layout
(`csvs/` with `ratios/` for robot inputs and `uvvis/` for reader exports, driven by `production/run_bo.sh`) works too:
files are looked up in the folder and those two subfolders, and a round counts once its `results_roundN_wells.csv`
exists, so a round that is laid out but not yet measured is skipped. Rounds, plates and
mixture counters are numbered from the values in `production/config.toml` (0, 0 and 1 in production); solute and solvent
names come from the plate map, so the same commands run on the older 1-based toy campaigns.

### `reduce` options

| Flag | Default | Effect |
|---|---|---|
| `--reader` | required | one reader export per sample plate, in plate order |
| `--blank` | none | optional export of a solvent-only copy of the sample plate (no blanks are run at the moment) |
| `--outdir` | next to the plate map | where the outputs go |
| `--wavelength Glutarimide=275 ...` | config, else picked | fix a solute's wavelength (wins over `wavelength_nm` in `production/config.toml`) |
| `--nm-range MIN MAX` | 230 800 | search peaks only in this range |
| `--bandwidth` | 0 | average over ± this many nm around the wavelength |
| `--blank-max` | 1.0 | with `--blank`: read only where every solvent blank is below this absorbance |
| `--abs-max` | 2.5 | flag wells whose raw absorbance exceeds this (reader linear range) |
| `--plots` | off | also write `spectra_roundN.png` and `plates_roundN.png` |

Each solute is read at its **fixed wavelength** (`wavelength_nm` in `production/config.toml`, or `--wavelength`). When none
is set it is read at the **peak of its DMF-control spectrum** (controls averaged over all plates, 5 nm smoothing).
**With no blanks that peak is the raw spectrum's, and DMF's own UV edge (below about 270 nm) can win**: the run prints a
warning, so set the wavelengths before the first real round. With a `--blank` plate, the peak is restricted to the
**usable window** (wavelengths where every solvent blank stays below `--blank-max`; acetone is opaque below about
330 nm), and a band maximum outside it is read on its shoulder. `wavelengths_roundN.csv` records `band_max_nm`,
`at_band_max`, the window, `signal_fraction` and a `measurable` verdict (control signal above 3 x the 600–800 nm noise).
Endpoint files carry `blank_abs` and a `flag` column (`saturated`, `opaque`); `bo_bridge.py merge` reads only the
absorbance. See PLAN.md decision 15.

**Blank handling.** **No blanks are run for now** (decision of the user, 2026-10-20; to be revisited): nothing is
subtracted, and the solvent's own absorbance stays in every well. If a solvent-only plate is read later, pass it as
`--blank`: it is used in `reduce` only to find the peaks, and `bo_bridge.py merge --blank` does the one subtraction.

### `qc` and `report` options

| Flag | Default | Effect |
|---|---|---|
| `--run` | required | the campaign folder |
| `--outdir` | `<run>/figures` | figures and summary |
| `qc --abs-max` | 2.5 | reader linear range: raw absorbance above it is flagged as saturated |
| `report --arms` | off | one report per arm of `production/config.toml` in `<outdir>/<arm>/`: each arm's objective (phthalimide alone; the minimum of the other three) replaces the all-solute one, because after round 0 the arms share no conditions |
| `report --no-gp` | off | skip the SDL_BO Gaussian-process landscape (needs `SDL_BO` and a few seconds per solute) |
| `report --seed` | 0 | seed for the GP fits |

## File formats

**Reader exports** (input): a long table with columns `well`, `wavelength_nm`, `absorbance` (any numeric column
name), a wide matrix with a wavelength column (`wavelength_nm`, `Wavel.`, ...) and one column per well, or its
transpose with one row per well and the wavelengths across the header (the plate reader's own export). `,` or `;`
separators (`;` implies decimal commas). Well names may be `A1` or `A01`. The planned scans are 200-700 nm in 5 nm
steps on 96 wells; a few fixed wavelengths also work (include one near 700 nm for the noise check).

**Plate log** (lab notes, optional): `plate_log_roundN.csv` with `plate` (0, 1, 2) and `read_delay_min`.

**Endpoint exports** (output of `reduce`): `well`, `absorbance`, the "well table" format `bo_bridge.py merge` reads.

## Use from Python

```python
from analysis.run import Run
from analysis.qc import run_qc
from analysis.report import run_report
run = Run("runs/r1")                 # plate maps, per-well results, datasets, spectra, plate log
arm = Run("runs/r1", ["Phthalimide"])   # one arm's view: only those solutes, so every objective is theirs
run_qc(run, Path("runs/r1/figures"))
run_report(run, Path("runs/r1/figures"), with_gp=True)
run.pooled()                         # one row per solute x mixture, pooled over rounds
run.pooled_objective()               # one row per mixture: rel per solute, worst-solute objective
```

## What is inside

| File | Role |
|---|---|
| `spectra.py` | Reading exports, optional blank correction, wavelength picking, reduction to one value per well. |
| `run.py` | A campaign folder as one object; condition kinds from ids; pooling across rounds. |
| `qc.py` | Q1, Q2, Q4–Q6 checks and figures, `qc_summary.md`. |
| `report.py` | R1–R7 analyses and figures, `report_summary.md`. |
| `plots.py` | Palette, plate heat maps, ternary helpers, the `reduce` figures. |
| `summary.py` | Markdown writer for the summaries. |
| `cli.py`, `__main__.py` | Command line. |
| `examples/` | Fake plate reader, round-0 example exports (3 plates, blank, plate log) and `make_toy_run.py` for a whole fake campaign; see its README. |
| `PLAN.md` | What is analysed, why, and the decisions to review. |
