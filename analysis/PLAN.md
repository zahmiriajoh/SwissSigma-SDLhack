# Analysis and figure plan

Agreed on 2026-10-20 (all items kept; the annotated draft is in git history) and implemented as
`python -m analysis qc` and `python -m analysis report`. **Revised later that day: the QC plate (solvent blanks and
calibration series) was dropped, so Q3 and Q7 and the blank subtraction are gone for now; see "Revision" at the end.** Your answers to the questions are recorded under
**Answers**; choices I made while implementing that you should look over are under **Decisions for review**.

Inputs, all produced by the existing pipeline, in one campaign folder (see `README.md`):

| File | From | Used for |
|---|---|---|
| `reader_roundN_plate{0,1,2}.csv` (optionally `reader_roundN_blank.csv`) | plate reader | spectral QC, wavelength choice |
| `results_roundN_wells.csv` | `bo_bridge.py merge` | per well and plate: `abs_raw`, `abs_blank`, `abs_corrected`, `rel_to_DMF` |
| `bo_dataset.csv` | `bo_bridge.py merge` | per solute × condition: fractions, `n_obs`, `abs_mean/std`, `rel_mean/std` |
| `bo_dataset_shared.csv` | `bo_bridge.py merge` | per condition: `rel_<solute>_mean`, `obj_min_rel`, `obj_mean_rel` |
| `condition_id` in `bo_dataset.csv` | SDL_BO naming | kind of condition: `R<round>_seed01`, `R<round>_exploit01`, `R<round>_explore01`; a re-test keeps its original id, so it shows up in a later round |
| `plate_log_roundN.csv` | lab notes | shake-end-to-read minutes per plate (optional; no check reads it since Q3 was dropped) |
| SDL_BO fitted GPs | `SDL_BO.campaign.fit_per_solute` (import) | posterior mean and uncertainty over the composition simplex |

Figure conventions: one Okabe-Ito colour per solute throughout, `viridis` for maps, a marker or
line-style cue wherever two categories meet, round number on every title, PNG at 300 dpi.

## Part 1: experiment quality (`analysis qc`)

| | Figure(s) | Numbers in `qc_summary.md` |
|---|---|---|
| **Q1 plate-to-plate reproducibility** | `qc_Q1_plates_roundN.png`: per solute, plate 1 vs the others, plus the CV histogram | median CV per solute and round; plates offset by more than 5 % are flagged |
| **Q2 control stability** | `qc_Q2_controls.png`: DMF control per solute, plate and round | max drift vs round 1; within-round CV |
| **Q4 spectral QC** | `qc_Q4_peakshift_roundN.png`, `qc_Q4_scatter_roundN.png`: 8×12 maps per plate | saturated wells (raw > `--abs-max`), wells with peak shift > 10 nm, max scattering 600–800 nm |
| **Q5 precision against signal** | `qc_Q5_precision.png`: std vs mean per condition, detection limit dashed | detection limit = 3 × the reader noise (600–800 nm spread of the control spectrum); fraction below it; log slope |
| **Q6 cross-round re-tests** | `qc_Q6_retests.png`: re-test vs first value, ± 2 CV band | mean absolute difference; fraction within 2 × that solute's CV |

## Part 2: the BO study aims (`analysis report`)

| | Figure(s) | Numbers in `report_summary.md` |
|---|---|---|
| **R1 mixtures vs single solvents, per solute** | `report_R1_per_solute.png`: pure solvents and the top 10 mixtures, DMF = 1 | best mixture vs best pure solvent, ratio, z against the combined error |
| **R2 the "dissolves everything" objective** | `report_R2_objective.png`: every mixture ranked by worst-solute solubility, coloured by number of solvents | top 10 table; whether a mixture beats the best single solvent (z > 2) |
| **R3 BO progress** | `report_R3_progress.png`: best so far per round; every condition by kind | n / mean / best per round and kind |
| **R4 composition landscape** | `report_R4_ternary.png`, `report_R4_gp.png`, `report_R4_binaries.png` | most-sampled trios and their counts |
| **R5 synergy** | `report_R5_synergy.png`: synergy vs balance; mean synergy per solvent pair | mean and max synergy per solute, most synergistic mixture |
| **R6 agreement between solutes** | `report_R6_solutes.png`: correlation matrix; top 10 across solutes | Pearson correlations |
| **R7 dataset** | `report_R7_dataset.png`: all conditions × solutes, grouped by round | row count and the deliverable file list |

## Answers (2026-10-20)

- **Q-a blank plate and calibration:** first answered as one extra QC plate per round (solvent blanks and a calibration series). **Withdrawn 2026-10-20: no extra plate and no calibration series. Blanks came back the same day as one pure-solvent well per solvent per round (see "Revision"); only the sample wells otherwise.**
- **Q-b solutes and reader:** solutes and solvents are now fixed in `production/config.toml` (Glutarimide, Boc-hydroxyproline, Phthalimide, Succinimide; DMF, acetone, EtOH, i-PrOH, water, i-PrOAc, t-BuOAc; numbering from zero). Still unknown (**remind the user**): the solutes' absorption maxima, the reader's linear range and export format. Assume a range of absorbance values to test the full range; assume fixed wavelengths. See `production/README.md` for the UV-readout and immiscibility concerns.
- **Q-c timing:** shake-end-to-read time will be recorded per plate.
- **Q-d solid loading:** same mass in every well, recorded.
- **Branched campaign (2026-10-20):** after the shared round 0 the campaign splits into two arms (`[[arms]]` in `production/config.toml`).
  `analysis report --arms` writes one report per arm (R1–R7 on that arm's solutes only, `Run(folder, solutes)`), so R2 and R3 show
  the objective each arm optimises: phthalimide alone, and the minimum of the other three. Without `--arms` the report is
  the all-solute one, which after round 0 covers only the seed mixtures. Q1–Q6 stay per solute and need no split.
- **Q-e priorities:** Q1, Q2, R2, R1, R3, Q4, R4, R5, Q5, Q6, R6, R7 (Q3 and Q7 dropped with the QC plate).
- **Q-f output:** PNG at 300 dpi plus `qc_summary.md` and `report_summary.md`; **ask again about slides later**.

## Decisions for review

1. **Dropped: QC plate layout** (7 solvents × 4 solutes × 2 loadings plus blanks). See "Revision".
2. **Dropped: blank per sample well** from the QC plate's pure-solvent wells. A solvent-only copy of the sample plate is still
   accepted via `--blank`.
3. **Blank subtraction stays in `bo_bridge.py merge`** (with `--blank`). `reduce` writes raw endpoint values, so the dataset keeps
   `abs_raw`, `abs_blank` and `abs_corrected` separately; with no blank, `abs_blank` is 0.
4. **Fixed wavelengths:** read at each solute's peak **plus 700 nm** so the scattering check (Q4) still works. The peak-shift
   map needs full spectra and is skipped otherwise. Peak picking on a few wavelengths uses no smoothing.
5. **Saturation threshold** `--abs-max` defaults to 2.5 absorbance until the reader's linear range is known (Q-b).
6. **Peak-shift masking:** wells whose blank-corrected band is below 0.05 absorbance are left grey in the peak-shift map,
   otherwise the UV edge wins the argmax for weak wells and every low-solubility well looks shifted.
7. **Dropped: calibration metrics** (Q7), with the calibration series.
8. **Pooling across rounds and the error model** (`Run.pooled`): a mixture measured in several rounds (re-tests) is
   averaged. Its error is a standard error built from a **pooled** per-solute per-well noise (root mean square of
   `rel_std` over all conditions; a 3-well std of one condition is far too uncertain to divide by), so within-round
   SE = noise / sqrt(n_obs), taken as the larger of that and the between-round spread, and combined in quadrature with
   the normalisation error rel × (relative drift of the DMF-control mean between rounds, or the control's SE if larger),
   because every value of a round is divided by that round's control. Campaigns without replicate plates fall back to
   the re-test spread, then to a 1 % noise floor. The "beats" tests in R1 and R2 and the synergy significance in R5 use
   z > 2 on that error (synergy's error also includes the pure solvents' errors scaled by their fractions).
9. **Condition kind** is parsed from `condition_id` (`seed`/`grid`, `exploit`, `explore`; an id from an earlier round = `retest`).
10. **Plate log format:** `plate_log_roundN.csv` with columns `plate` (0, 1, 2) and `read_delay_min`. Only Q3 plotted the plate
    median against it, so nothing reads the file at the moment. Add more columns freely.
11. **Toy data** (`analysis/examples/make_toy_run.py`): no SDL_BO, random seeded suggestions in SDL_BO's id scheme and
    within the trough budget, band heights 2.6 / 1.2 / 0.5 / 0.06 in production solute order (the first saturates, the last sits near the noise), plate attack by
    esters, ethers and DMF growing with the read delay. `examples/toy_additive_pipeline.py` (sdl_merge) remains the
    full-pipeline run with the real BO.
12. **GP landscape** fits SDL_BO's per-solute GPs on `bo_dataset.csv` and plots the minimum over solutes of the posterior
    means (the objective's posterior mean, approximately) and the mean posterior std, over 2.5 % grids of the three
    most-sampled solvent trios. `--no-gp` skips it.
13. **Reader export format** (`analysis/spectra.py`, `read_spectra`): three shapes are accepted, a long table with columns
    `well`, `wavelength_nm` and one numeric absorbance column (any name), a wide matrix with a wavelength column and one
    column per well, or its transpose (one row per well, wavelengths across the header), which is how the plate reader
    exports (`production/UV-Vis/Absorbancescan.csv`, first header `Wavel.`). `;`-separated files with decimal commas are
    read too; well names may be `A1` or `A01`. The real scans will be 200-700 nm in 5 nm steps on full 96-well plates;
    a scan with steps up to 5 nm counts as a full spectrum, and the peak-picking smoothing is 5 nm wide but at least
    3 points. Wavelengths fixed in `production/config.toml` should lie on the 5 nm grid. The accepted formats are documented
    in `README.md` ("File formats").
14. **Forbidden solvent pairs** (user decision): water + iPrOAc and water + tBuOAc are immiscible and listed in
    `production/config.toml`; `is_allowed()` is applied in SDL_BO's search space, bo_bridge's seed grid and layout check
    and the toy generator. See `production/README.md`.
15. **Conservative readout: read only where every solvent is transparent** (user request, since the plan cannot change
    once the campaign starts). `analysis reduce` derives a usable wavelength window from the blank spectra: wavelengths
    where the worst blank well (`--blank`) stays below `--blank-max` (default 1.0
    absorbance, leaving headroom for the solute below the reader's limit). Each solute's wavelength is the peak of its
    DMF-control spectrum **inside that window**; if the band maximum lies outside (e.g. under acetone's 330 nm cut-off)
    the solute is read on its shoulder and `wavelengths_roundN.csv` records `at_band_max = False`, the band maximum,
    the window and `signal_fraction`. A solute whose control signal at that wavelength is below 3 x the spectral noise
    (600-800 nm spread) is marked `measurable = False`, and the console says so. Endpoint files carry `blank_abs` and a
    `flag` column (`saturated` above `--abs-max`, `opaque` above `--blank-max`) that bo_bridge merge ignores.
    Consequences: measurements stay valid in every well at the cost of sensitivity; a solute that cannot be measured is
    declared unmeasurable up front rather than reported as insoluble, and a solute flagged in **any** round is excluded
    from the worst-solute objective by both `analysis report` (`Run.measurable_solutes`) and SDL_BO's scoring
    (`SDL_BO.dataset.unmeasurable_solutes`), while staying in the data and fits. **This needs a blank (`--solvent-blanks` or `--blank`), so it is inactive without one**
    (see "Revision"); read `wavelengths_round0.csv` after round 0 for which solutes the UV readout can follow at all.
    Prefer full-spectrum exports; with fixed wavelengths, take the maxima from the literature or a first spectrum, plus 700 nm.

## Revision (2026-10-20): QC plate removed

The user dropped the QC plate: only the main sample wells are run. Consequences, to revisit when blanks are added back:

- `analysis qc-layout`, `--qc-reader` / `--qc-map`, `qc_layout.py`, Q3 (blank wells, plate attack, read delay, additivity)
  and Q7 (calibration) are gone. Q5's detection limit is now 3 × the reader noise from `wavelengths_roundN.csv`.
- **Update (2026-10-20, later): blanks are back as pure-solvent wells.** One well per solvent each round (A1 DMF ... G1 tBuOAc, `reader_roundN_solvents.csv`, `reduce --solvent-blanks`); each sample well's blank is the volume-fraction-weighted sum of them. Decision 15's window and flags are active again when the file is given; the bullets below describe the run without it.
- **Without a blank nothing is subtracted**, so every well includes its solvent's own absorbance (acetone absorbs below about 330 nm, DMF
  below about 270 nm). Decision 15's usable-window machinery needs a blank (`--blank`) and is inactive without one.
- **Wavelengths must be set.** With no blank and no `wavelength_nm` in `production/config.toml` the peak is picked on the raw
  DMF-control spectrum and lands on DMF's own UV edge (about 230 nm, saturated) for most solutes; `reduce` prints a warning.
  Set the absorption maxima in the config before the first real round.
- The toy run now passes the fake solutes' known peaks as fixed wavelengths, so its "band hidden under acetone's cut-off"
  scenario is no longer detected as not measurable; acetone wells instead saturate at that solute's read (Q4).
