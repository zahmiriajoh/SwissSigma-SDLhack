# analysis

**Plate-reader spectra in; endpoint files for `bo_bridge.py merge`, QC figures and the study report out.**
Four commands, all run from the repo root with `python -m analysis ...`:

| Command | In | Out |
|---|---|---|
| `qc-layout` | `plate_map_roundN.csv` | QC plate map + robot CSV (blanks and calibration series) |
| `reduce` | reader exports of the sample plates + QC plate (or blank plate), plate map | one `(well, absorbance)` file per plate at each solute's wavelength, `wavelengths_roundN.csv` |
| `qc` | a campaign folder | experiment-quality figures Q1–Q7 and `qc_summary.md` |
| `report` | a campaign folder | study-aim figures R1–R7 and `report_summary.md` |

What each figure shows and the decisions behind them are in [`PLAN.md`](PLAN.md).

## Install

Part of the repo-wide `sdlhack` environment (`mamba env create -f ../environment.yml`): Python 3.12,
`numpy`, `pandas`, `matplotlib`; `report` imports `SDL_BO` for the Gaussian-process landscape.

## One round

```
bo_bridge.py layout ──► plate_map_roundN.csv ──► analysis qc-layout ──► qc_plate_map_roundN.csv, ot_input_roundN_qc.csv
OT-2: 3 sample plates (ot_input_roundN.csv) + 1 QC plate (ot_input_roundN_qc.csv, 1-plate run)
plate reader ──► reader_roundN_plate{1,2,3}.csv, reader_roundN_qc.csv        lab ──► plate_log_roundN.csv
analysis reduce ──► endpoint_roundN_plate{1,2,3}.csv, endpoint_roundN_blank.csv, wavelengths_roundN.csv
bo_bridge.py merge --reader endpoint_... --blank endpoint_roundN_blank.csv ──► results_roundN_wells.csv, bo_dataset.csv
analysis qc / report (any time, all rounds so far)
```

```bash
python -m analysis qc-layout --plate-map runs/prod/plate_map_round0.csv
python -m analysis reduce --plate-map runs/prod/plate_map_round0.csv --reader runs/prod/reader_round0_plate{0,1,2}.csv \
    --qc-reader runs/prod/reader_round0_qc.csv --qc-map runs/prod/qc_plate_map_round0.csv --plots
python "OT protocols/bo_bridge.py" merge --plate-map runs/prod/plate_map_round0.csv \
    --reader runs/prod/endpoint_round0_plate{0,1,2}.csv --blank runs/prod/endpoint_round0_blank.csv --dataset runs/prod/bo_dataset.csv
python -m analysis qc --run runs/prod
python -m analysis report --run runs/prod
```

Keep every round of a campaign in **one folder** (the `--outdir` of `layout`, `reduce` and `merge`): `qc` and `report`
find the rounds from the `plate_map_roundN.csv` files there and write to `<folder>/figures/`. Rounds, plates and
condition counters are numbered from the values in `production/config.toml` (zero in production); solute and solvent
names come from the plate map, so the same commands run on the older 1-based toy campaigns.

### `reduce` options

| Flag | Default | Effect |
|---|---|---|
| `--reader` | required | one reader export per sample plate, in plate order |
| `--qc-reader`, `--qc-map` | none | QC plate export and map: each sample well's blank is the volume-weighted sum of the pure-solvent blank wells |
| `--blank` | none | alternative: export of a solvent-only copy of the sample plate |
| `--outdir` | next to the plate map | where the outputs go |
| `--wavelength Glutarimide=275 ...` | picked | fix a solute's wavelength instead of picking it |
| `--nm-range MIN MAX` | 230 800 | search peaks only in this range |
| `--bandwidth` | 0 | average over ± this many nm around the wavelength |
| `--blank-max` | 1.0 | usable window: read only where every solvent blank is below this absorbance |
| `--abs-max` | 2.5 | flag wells whose raw absorbance exceeds this (reader linear range) |
| `--plots` | off | also write `spectra_roundN.png` and `plates_roundN.png` |

Each solute is read at the **peak of its DMF-control spectrum** (controls averaged over all plates, blank subtracted,
5 nm smoothing), restricted to the **usable window**: wavelengths where every pure-solvent blank (QC plate) or every
blank well stays below `--blank-max`, so no well is read where its own solvent saturates the detector. If a band
maximum lies outside the window (acetone is opaque below about 330 nm, DMF below about 270 nm) the solute is read on
its shoulder; `wavelengths_roundN.csv` records `band_max_nm`, `at_band_max`, the window, `signal_fraction` and a
`measurable` verdict (control signal above 3 x the 600–800 nm noise). With a reader set to a few fixed wavelengths the
peak is simply the best usable one. Pass `--wavelength` to override, or to read later rounds at the round-0 values.
Endpoint files carry `blank_abs` and a `flag` column (`saturated`, `opaque`); `bo_bridge.py merge` reads only the
absorbance. See PLAN.md decision 15.

**Blank handling.** The blank is used in `reduce` only to find the peaks. The endpoint files keep raw absorbance for the
plates and the blank alike, so `bo_bridge.py merge --blank` does the one and only subtraction.

### `qc` and `report` options

| Flag | Default | Effect |
|---|---|---|
| `--run` | required | the campaign folder |
| `--outdir` | `<run>/figures` | figures and summary |
| `qc --abs-max` | 2.5 | reader linear range: raw absorbance above it is flagged as saturated |
| `report --no-gp` | off | skip the SDL_BO Gaussian-process landscape (needs `SDL_BO` and a few seconds per solute) |
| `report --seed` | 0 | seed for the GP fits |

## File formats

**Reader exports** (input): a long table with columns `well`, `wavelength_nm`, `absorbance` (any numeric column
name), or a wide matrix with `wavelength_nm` in the first column and one column per well. Well names may be `A1` or
`A01`. Full spectra or a few fixed wavelengths both work; include a reading near 700 nm in fixed mode so the scattering
check has data. These shapes were chosen before any real export existed: run the instrument's first file through
`reduce` before the first round (PLAN.md, decision 13).

**QC plate map** (`qc-layout`): `well, round, role (calibration | blank), solvent, solute, loading, condition_id,
frac_<solvent>, vol_<solvent>_ul`. Calibration wells carry `loading` × the nominal solid mass in one pure solvent;
blank wells carry no solid (pure solvents, equal binaries and ternaries).

**Plate log** (lab notes, optional): `plate_log_roundN.csv` with `plate` (1, 2, 3, qc) and `read_delay_min`.

**Endpoint exports** (output of `reduce`): `well`, `absorbance`, the "well table" format `bo_bridge.py merge` reads.

## Use from Python

```python
from analysis.run import Run
from analysis.qc import run_qc
from analysis.report import run_report
run = Run("runs/r1")                 # plate maps, per-well results, datasets, spectra, QC plate, plate log
run_qc(run, Path("runs/r1/figures"))
run_report(run, Path("runs/r1/figures"), with_gp=True)
run.pooled()                         # one row per solute x mixture, pooled over rounds
run.pooled_objective()               # one row per mixture: rel per solute, worst-solute objective
```

## What is inside

| File | Role |
|---|---|
| `spectra.py` | Reading exports, blank correction, synthetic blank from the QC plate, wavelength picking, reduction to one value per well. |
| `qc_layout.py` | The QC plate: map and robot CSV. |
| `run.py` | A campaign folder as one object; condition kinds from ids; pooling across rounds. |
| `qc.py` | Q1–Q7 checks and figures, `qc_summary.md`. |
| `report.py` | R1–R7 analyses and figures, `report_summary.md`. |
| `plots.py` | Palette, plate heat maps, ternary helpers, the `reduce` figures. |
| `summary.py` | Markdown writer for the summaries. |
| `cli.py`, `__main__.py` | Command line. |
| `examples/` | Fake plate reader, round-1 example exports (3 plates, blank, QC plate, plate log) and `make_toy_run.py` for a whole fake campaign; see its README. |
| `PLAN.md` | What is analysed, why, and the decisions to review. |
