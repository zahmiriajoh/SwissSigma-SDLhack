# Analysis and figure plan

Agreed on 2026-10-20 (all items kept; the annotated draft is in git history) and implemented as
`python -m analysis qc` and `python -m analysis report`. Your answers to the questions are recorded under
**Answers**; choices I made while implementing that you should look over are under **Decisions for review**.

Inputs, all produced by the existing pipeline, in one campaign folder (see `README.md`):

| File | From | Used for |
|---|---|---|
| `reader_roundN_plate{1,2,3}.csv`, `reader_roundN_qc.csv` (or `reader_roundN_blank.csv`) | plate reader | spectral QC, blank, calibration |
| `results_roundN_wells.csv` | `bo_bridge.py merge` | per well and plate: `abs_raw`, `abs_blank`, `abs_corrected`, `rel_to_DMF` |
| `bo_dataset.csv` | `bo_bridge.py merge` | per solute × condition: fractions, `n_obs`, `abs_mean/std`, `rel_mean/std` |
| `bo_dataset_shared.csv` | `bo_bridge.py merge` | per condition: `rel_<solute>_mean`, `obj_min_rel`, `obj_mean_rel` |
| `condition_id` in `bo_dataset.csv` | SDL_BO naming | kind of condition: `R<round>_seed01`, `R<round>_exploit01`, `R<round>_explore01`; a re-test keeps its original id, so it shows up in a later round |
| `qc_plate_map_roundN.csv`, `plate_log_roundN.csv` | `analysis qc-layout`, lab notes | QC plate roles and loadings; shake-end-to-read minutes per plate |
| SDL_BO fitted GPs | `SDL_BO.campaign.fit_per_solute` (import) | posterior mean and uncertainty over the composition simplex |

Figure conventions: one Okabe-Ito colour per solute throughout, `viridis` for maps, a marker or
line-style cue wherever two categories meet, round number on every title, PNG at 300 dpi.

## Part 1: experiment quality (`analysis qc`)

| | Figure(s) | Numbers in `qc_summary.md` |
|---|---|---|
| **Q1 plate-to-plate reproducibility** | `qc_Q1_plates_roundN.png`: per solute, plate 1 vs the others, plus the CV histogram | median CV per solute and round; plates offset by more than 5 % are flagged |
| **Q2 control stability** | `qc_Q2_controls.png`: DMF control per solute, plate and round | max drift vs round 1; within-round CV |
| **Q3 blank wells and plate attack** | `qc_Q3_blank.png`: blank by dominant solvent, vs ester+ether fraction, plate median vs read delay, QC-plate mixture blanks vs additive prediction | additive blank model per solute (`b_<solvent>`, residual std, R²); mean additivity error |
| **Q4 spectral QC** | `qc_Q4_peakshift_roundN.png`, `qc_Q4_scatter_roundN.png`: 8×12 maps per plate | saturated wells (raw > `--abs-max`), wells with peak shift > 10 nm, max scattering 600–800 nm |
| **Q5 precision against signal** | `qc_Q5_precision.png`: std vs mean per condition, detection limit dashed | detection limit = 3 × blank residual std; fraction below it; log slope |
| **Q6 cross-round re-tests** | `qc_Q6_retests.png`: re-test vs first value, ± 2 CV band | mean absolute difference; fraction within 2 × that solute's CV |
| **Q7 calibration (QC plate)** | `qc_Q7_calibration_roundN.png`: blank-corrected absorbance vs loading, per solute and solvent | slope per unit mass, top-to-bottom linearity, linear range, DMF-control recovery |

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

- **Q-a blank plate and calibration:** one extra plate every round with solvent-only blanks and a calibration series for each pure solvent–solute pair. Implemented as the QC plate (`analysis qc-layout`).
- **Q-b solutes and reader:** solutes and solvents are now fixed in `production/config.toml` (Glutarimide, Boc-hydroxyproline, Phthalimide, Succinimide; DMF, acetone, EtOH, i-PrOH, water, i-PrOAc, t-BuOAc; numbering from zero). Still unknown (**remind the user**): the solutes' absorption maxima, the reader's linear range and export format. Assume a range of absorbance values to test the full range; assume fixed wavelengths. See `production/README.md` for the UV-readout and immiscibility concerns.
- **Q-c timing:** shake-end-to-read time will be recorded per plate.
- **Q-d solid loading:** same mass in every well, recorded.
- **Q-e priorities:** Q1, Q2, R2, R1, R3, Q3, Q4, R4, R5, Q5, Q6, R6, R7, Q7.
- **Q-f output:** PNG at 300 dpi plus `qc_summary.md` and `report_summary.md`; **ask again about slides later**.

## Decisions for review

1. **QC plate layout** (`analysis/qc_layout.py`): 7 solvents × 4 solutes × 2 loadings (0.5 and 1.0 × the nominal mass)
   = 56 calibration wells, plus 40 blanks: the 7 pure solvents, all 15 equal binaries and 18 of the 20 equal ternaries.
   Change `--loadings` for more levels (3 levels = 84 calibration wells, 12 blanks). The scientists weigh
   `loading × nominal mass` into each calibration well; the robot adds 300 µL of the pure solvent from
   `ot_input_roundN_qc.csv`, run as a separate 1-plate run of the OT-2 protocol.
2. **Blank per sample well** = volume-weighted sum of the QC plate's pure-solvent blank spectra (`synthetic_blank`).
   This replaces the earlier full solvent-only copy of the sample plate, which is still accepted via `--blank`.
   The mixture blanks on the QC plate test this additivity assumption (Q3, last panel).
3. **Blank subtraction stays in `bo_bridge.py merge`.** `reduce` writes raw endpoint values for the plates and the
   synthetic blank, so the dataset keeps `abs_raw`, `abs_blank` and `abs_corrected` separately.
4. **Fixed wavelengths:** read at each solute's peak **plus 700 nm** so the scattering check (Q4) still works. The peak-shift
   map needs full spectra and is skipped otherwise. Peak picking on a few wavelengths uses no smoothing.
5. **Saturation threshold** `--abs-max` defaults to 2.5 absorbance until the reader's linear range is known (Q-b).
6. **Peak-shift masking:** wells whose blank-corrected band is below 0.05 absorbance are left grey in the peak-shift map,
   otherwise the UV edge wins the argmax for weak wells and every low-solubility well looks shifted.
7. **Calibration metrics:** with two loading levels an R² is meaningless, so Q7 reports the slope from the lowest loading
   (most likely fully dissolved), the top-to-bottom linearity ratio (1.0 = proportional, well below 1 = solubility-limited)
   and the largest loading within 5 % of that line. `dmf_control_recovery` = sample-plate DMF control / DMF slope.
8. **Pooling across rounds and the error model** (`Run.pooled`): a mixture measured in several rounds (re-tests) is
   averaged. Its error is a standard error built from a **pooled** per-solute per-well noise (root mean square of
   `rel_std` over all conditions; a 3-well std of one condition is far too uncertain to divide by), so within-round
   SE = noise / sqrt(n_obs), taken as the larger of that and the between-round spread, and combined in quadrature with
   the normalisation error rel × (relative drift of the DMF-control mean between rounds, or the control's SE if larger),
   because every value of a round is divided by that round's control. Campaigns without replicate plates fall back to
   the re-test spread, then to a 1 % noise floor. The "beats" tests in R1 and R2 and the synergy significance in R5 use
   z > 2 on that error (synergy's error also includes the pure solvents' errors scaled by their fractions).
9. **Condition kind** is parsed from `condition_id` (`seed`/`grid`, `exploit`, `explore`; an id from an earlier round = `retest`).
10. **Plate log format:** `plate_log_roundN.csv` with columns `plate` (1, 2, 3, qc) and `read_delay_min`. Q3 plots the plate
    median against it. Add more columns freely; only these two are read.
11. **Toy data** (`analysis/examples/make_toy_run.py`): no SDL_BO, random seeded suggestions in SDL_BO's id scheme and
    within the trough budget, band heights 2.6 / 1.2 / 0.5 / 0.06 in production solute order (the first saturates, the last sits near the noise), plate attack by
    esters, ethers and DMF growing with the read delay. `examples/toy_additive_pipeline.py` (sdl_merge) remains the
    full-pipeline run with the real BO.
12. **GP landscape** fits SDL_BO's per-solute GPs on `bo_dataset.csv` and plots the minimum over solutes of the posterior
    means (the objective's posterior mean, approximately) and the mean posterior std, over 2.5 % grids of the three
    most-sampled solvent trios. `--no-gp` skips it.
13. **Reader export format** (`analysis/spectra.py`, `read_spectra`): two shapes are accepted, a long table with columns
    `well`, `wavelength_nm` and one numeric absorbance column (any name), or a wide matrix with `wavelength_nm` as the first
    column and one column per well; well names may be `A1` or `A01`. Both were chosen from invented files. **The first
    real export must be run through `analysis reduce` before the first round**; if the instrument writes another shape
    (one block per wavelength, extra header rows, a different wavelength column name) the parser needs a small
    addition. The accepted formats are documented in `README.md` ("File formats").
14. **Forbidden solvent pairs** (user decision): water + iPrOAc and water + tBuOAc are immiscible and listed in
    `production/config.toml`; `is_allowed()` is applied in SDL_BO's search space, bo_bridge's seed grid and layout check,
    the QC plate's mixture blanks (89 wells used) and the toy generator. See `production/README.md`.
