# Analysis and figure plan

Draft for discussion. Each item has a **Decision:** line (keep / drop / change, plus priority) and
the questions at the end have **Answer:** lines. Annotate in place; the plan gets trimmed to what
we agree on and then implemented as `python -m analysis qc` and `python -m analysis report`.

Inputs, all produced by the existing pipeline:

| File | From | Used for |
|---|---|---|
| `reader_roundN_plate{1,2,3}.csv`, `reader_roundN_blank.csv` | plate reader | spectral QC |
| `results_roundN_wells.csv` | `bo_bridge.py merge` | per well and plate: `abs_raw`, `abs_blank`, `abs_corrected`, `rel_to_DMF` |
| `bo_dataset.csv` | `bo_bridge.py merge` | per solute × condition: fractions, `n_obs`, `abs_mean/std`, `rel_mean/std` |
| `bo_dataset_shared.csv` | `bo_bridge.py merge` | per condition: `rel_<solute>_mean`, `obj_min_rel`, `obj_mean_rel` |
| `condition_id` in `bo_dataset.csv` | SDL_BO naming | kind of condition: `R<round>_seed01`, `R<round>_exploit01`, `R<round>_explore01`; a re-test keeps its original id, so it shows up in a later round |
| SDL_BO fitted GPs | `SDL_BO.campaign.fit_per_solute` (import) | posterior mean and uncertainty over the composition simplex |

Figure conventions: one Okabe-Ito colour per solute throughout, `viridis` for maps, a marker or
line-style cue wherever two categories meet, round number on every title.

## Part 1: experiment quality (`analysis qc`)

### Q1. Plate-to-plate reproducibility
The 3 identical plates per round are true replicates of every condition.
- Figure: per solute, corrected absorbance on plate 1 vs 2, 1 vs 3 (scatter, identity line), plus a
  histogram of the coefficient of variation per condition. One figure per round.
- Number: median CV per solute and per round. This is the noise floor BO has to beat.
- Flags: a plate whose values are offset from the other two.

**Decision:**

### Q2. Control stability
- Figure: DMF-control absorbance per solute against plate and round (points joined by round).
- Why: the control scales every relative value. Drift between rounds means different solid
  loading, evaporation or plate attack, and makes rounds hard to compare.

**Decision:**

### Q3. Blank plate and polystyrene attack
- Figure: blank-well absorbance at each solute's wavelength against solvent composition, grouped
  by dominant solvent (esters, ethers, MeCN, DMC, DMF). Second panel: blank absorbance against
  fraction of ester + ether.
- Why: a blank well with no solute that reads high is plate damage or solvent absorbance. It says
  how much to trust ester- and ether-rich mixtures and how large the blank correction is.

**Decision:**

### Q4. Spectral QC
- Figure A: peak position per well (argmax of the corrected spectrum) minus the picked wavelength,
  as an 8×12 map per plate. A shift means a solvatochromic effect or a wrong well.
- Figure B: scattering index (mean corrected absorbance 600–800 nm) as an 8×12 map per plate.
  High values mean undissolved solid in the light path, which inflates the reading.
- Figure C: saturation flag for wells above the reader's linear range (threshold from Q-b below).

**Decision:**

### Q5. Precision against signal
- Figure: `abs_std` against `abs_mean` per condition and solute (log axes), with the detection
  limit (3 × blank noise) as a line.
- Why: shows whether low-solubility conditions are measurable at all, and whether noise is
  proportional (pipetting) or constant (reader).

**Decision:**

### Q6. Cross-round reproducibility
SDL_BO re-tests the 5 best mixtures each round, so the same composition is measured on new solid
and a new plate.
- Figure: re-test `rel_mean` against the original value, per solute, coloured by round, with the
  identity line and the within-round CV band from Q1.
- Why: the only check that rounds, solid batches and reservoir refills are comparable.

**Decision:**

### Q7. Accuracy against a standard (only if calibration wells exist, see Q-a)
- Figure: calibration series absorbance against concentration, linear fit, residuals.
- Output: molar absorptivity per solute and the linear range, so relative solubility can be
  turned into an absolute concentration estimate for the DMF control.

**Decision:**

## Part 2: the BO study aims (`analysis report`)

### R1. Mixtures vs single solvents, per solute
- Figure: per solute, dot chart of the 6 pure solvents and the top 10 mixtures, `rel_mean` to DMF
  with `rel_std` bars, best single solvent marked, DMF = 1 as a line.
- Table: best mixture, best single solvent, their ratio and whether the difference exceeds the
  Q1 noise floor.

**Decision:**

### R2. The "dissolves everything" objective
- Figure: all shared conditions ranked by `obj_min_rel`, coloured by number of solvents, with
  lines for the best single solvent's `obj_min_rel` and for DMF (1.0). Error bars from the
  worst solute's `rel_std`.
- Why: this is the hypothesis test. One mixture beating every single solvent on its worst solute
  is the proposal's success criterion.

**Decision:**

### R3. BO progress
- Figure A: best `obj_min_rel` so far against round (step line), with the round-1 grid best as a
  baseline.
- Figure B: per round, distribution of `obj_min_rel` split by kind of condition (seed, exploit,
  explore, re-test; parsed from `condition_id`) as strip plots.
- Why: shows whether BO is learning, and whether exploit picks beat explore picks as they should.

**Decision:**

### R4. Composition landscape
- Figure A: ternary plots for the 3–4 most-sampled solvent trios, measured conditions as points
  coloured by `obj_min_rel`, binary edges included.
- Figure B: the GP posterior mean and standard deviation over the same simplices (needs SDL_BO's
  fit and predict functions; agreed with sdl_merge to import, not copy).
- Figure C: 6×6 matrix of the round-1 50:50 binaries, `obj_min_rel` as colour, pure solvents on
  the diagonal. A compact view of the whole seed grid.

**Decision:**

### R5. Synergy
- Measure: `rel_mean` of a mixture minus the fraction-weighted mean of its pure solvents' `rel_mean`
  (linear mixing rule). Positive = genuine mixture effect.
- Figure: synergy per condition and solute against mixture balance (1 − Σ fraction²), and a bar
  chart of mean synergy per solvent pair.

**Decision:**

### R6. Do the solutes agree?
- Figure: correlation matrix of `rel_mean` between solutes across all conditions, plus a
  parallel-coordinates plot of the top 10 conditions across the 4 solutes.
- Why: low correlation means "dissolves everything" is a real trade-off and explains why the
  min objective is hard.

**Decision:**

### R7. Deliverable dataset
- Figure: heat map of all conditions (rows, grouped by round) × solutes (columns), `rel_mean` as
  colour, `obj_min_rel` as a final column.
- Files: `bo_dataset.csv`, `bo_dataset_shared.csv`, plate maps and the QC summary table, as the
  open dataset the proposal promises.

**Decision:**

## Questions

**Q-a. Blank plate and calibration.** Will a solvent-only blank plate be run every round? Will a
calibration series of a reference standard be run, and if so in which wells and solvent? The
current layout has 1 DMF control + 23 conditions per solute and no calibration wells, so Q7 is
impossible unless wells are given to it.

**Answer:**

**Q-b. Solutes and reader.** What are the real four solutes (names for `SOLUTES` in
`bo_bridge.py`) and their expected absorption maxima? What is the plate reader's linear
absorbance range (for the saturation flag) and does it export full spectra or fixed wavelengths?

**Answer:**

**Q-c. Timing.** Will the time between end of shaking and plate reading be recorded per plate?
Polystyrene attack and evaporation grow with contact time, so I would use it as a covariate in Q3.

**Answer:**

**Q-d. Solid loading.** Is the same mass of each solute weighed into every well (so absorbance
tracks dissolved fraction), or does it vary? If it varies, is the mass recorded per well?

**Answer:**

**Q-e. Priorities.** Which of Q1–Q7 and R1–R7 matter most for the hackathon write-up? My proposed
order: Q1, Q2, R2, R1, R3, Q3, Q4, R4, R5, Q5, Q6, R6, R7, Q7.

**Answer:**

**Q-f. Output format.** Figures as PNG at 150 dpi in the run folder, plus a one-page
`qc_summary.md` and `report_summary.md` with the key numbers? Anything else needed (SVG, a
notebook, a slide-ready layout)?

**Answer:**
