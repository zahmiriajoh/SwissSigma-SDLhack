# analysis

**Plate-reader spectra in, one absorbance per well out.** The step between the UV-Vis reader and
`bo_bridge.py merge`: it reads the full-spectrum export of each plate, finds the wavelength to read
each solute at, and writes the single-value export per plate that `merge --reader` takes. It uses
the plate map from `bo_bridge.py layout` and nothing else from the robot side.

## Install

Part of the repo-wide `sdlhack` environment (`mamba env create -f ../environment.yml`): Python 3.12,
`numpy`, `pandas`, `matplotlib`. Run from the repo root with `python -m analysis ...`.

## The loop

```
plate reader ──► reader_roundN_plate{1,2,3}.csv (+ reader_roundN_blank.csv)
                              │
                              ▼
            python -m analysis reduce ──► endpoint_roundN_plate{1,2,3}.csv, endpoint_roundN_blank.csv
                                          wavelengths_roundN.csv (+ QC figures)
                              │
                              ▼
   python "OT protocols/bo_bridge.py" merge --reader endpoint_... --blank endpoint_..._blank.csv
```

```bash
python -m analysis reduce --plate-map "OT protocols/examples/plate_map_round1.csv" \
    --reader analysis/examples/reader_round1_plate{1,2,3}.csv \
    --blank analysis/examples/reader_round1_blank.csv --outdir runs/round1 --plots
```

`reduce` prints the `bo_bridge.py merge` command to run next.

| Flag | Default | Effect |
|---|---|---|
| `--plate-map` | required | `plate_map_roundN.csv` from `bo_bridge.py layout` (well, solute, role, ...) |
| `--reader` | required | one full-spectrum export per plate, in plate order |
| `--blank` | none | full-spectrum export of the solvent-only plate (same layout, no solids) |
| `--outdir` | next to the plate map | where the outputs go |
| `--wavelength S1=275 ...` | picked | fix a solute's wavelength instead of picking it |
| `--nm-range MIN MAX` | 230 800 | search peaks only in this range |
| `--bandwidth` | 0 | average over ± this many nm around the wavelength |
| `--plots` | off | also write `spectra_roundN.png` and `plates_roundN.png` |

## How the wavelength is chosen

Each solute is read at the **peak of its DMF-control spectrum**: the control wells of that solute are
averaged over all plates, the blank is subtracted so the solvent and plate baseline do not shift the
peak, a 5 nm rolling mean removes single-point noise, and the maximum inside `--nm-range` is taken.
The DMF control is the right place to look because it is the well where the solute is most likely
fully dissolved. Pass `--wavelength` to override, or when a solute has no control well. The picked
values are saved to `wavelengths_roundN.csv`, so later rounds can be read at the same wavelengths
with `--wavelength`.

**Blank handling.** The blank is used here only to find the peaks. The endpoint files keep the raw
absorbance for the plates and the blank alike, so `bo_bridge.py merge --blank` does the one and only
subtraction and `bo_dataset.csv` records `abs_raw`, `abs_blank` and `abs_corrected` separately.

## File formats

**Reader exports** (input): either a long table with columns `well`, `wavelength_nm`, `absorbance`
(any numeric column name works), or a wide matrix with `wavelength_nm` in the first column and one
column per well. Well names may be `A1` or `A01`. Every well in the plate map must be present.

**Endpoint exports** (output): `well`, `absorbance`, one row per plate-map well. This is the long
"well table" format `bo_bridge.py merge --reader` and `--blank` read.

**`wavelengths_roundN.csv`**: `solute`, `wavelength_nm`.

## QC figures (`--plots`)

- `spectra_roundN.png`: one panel per solute with every well of every plate (grey), the DMF controls
  in colour and the picked wavelength as a dashed line. Bands that do not line up, or a peak sitting on
  a sloping baseline, show up here.
- `plates_roundN.png`: 8×12 heat map of the endpoint absorbance of each plate and the blank, DMF
  controls ringed. Use it to spot a bad plate, an edge effect or a swapped plate order.

## Use from Python

```python
from analysis.spectra import read_plate_map, read_spectra, reduce_round

plate_map = read_plate_map("plate_map_round1.csv")
plates = [read_spectra(f"reader_round1_plate{i}.csv") for i in (1, 2, 3)]
wavelengths, endpoints, corrected = reduce_round(plate_map, plates, read_spectra("reader_round1_blank.csv"))
```

| Function | Returns |
|---|---|
| `read_spectra(path)` | wide DataFrame: index `wavelength_nm`, one column per well |
| `read_plate_map(path)` | plate map indexed by well |
| `blank_correct(spectra, blank)` | spectra minus the blank, well by well |
| `pick_wavelengths(corrected, plate_map, nm_range, overrides)` | Series: wavelength per solute |
| `reduce_plate(spectra, plate_map, wavelengths, bandwidth_nm)` | `(well, absorbance)` DataFrame |
| `reduce_round(plate_map, plates, blank, ...)` | `(wavelengths, endpoints, corrected)` |

`SpectraError` (a `ValueError`) is raised for unusable inputs.

## What is inside

| File | Role |
|---|---|
| `spectra.py` | Reading exports, blank correction, wavelength picking, reduction to one value per well. |
| `plots.py` | The two QC figures. |
| `cli.py`, `__main__.py` | Command line. |
| `examples/` | Synthetic round-1 spectra (3 plates + blank) and the generator that makes them; see its README. |
