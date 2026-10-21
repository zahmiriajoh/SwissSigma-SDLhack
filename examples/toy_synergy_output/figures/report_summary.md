# Report: toy_synergy_output (rounds 0, 1, 2)

## R1 mixtures vs single solvents, per solute

For each solute on its own, does any green-solvent mixture dissolve more than the best single green solvent, and how close does it come to DMF?

- z = difference over the combined error (within-plate and between-round spread); a mixture beats the best pure solvent when z > 2.

| solute | best_mixture | rel_mixture | best_pure | rel_pure | ratio | z | mixture_beats_pure |
|---|---|---|---|---|---|---|---|
| Boc-hydroxyproline | 0.333 EtOH + 0.333 iPrOH + 0.333 iPrOAc | 0.870 | 1 iPrOAc | 0.708 | 1.227 | 95.114 | True |
| Glutarimide | 0.5 acetone + 0.5 iPrOH | 1.113 | 1 acetone | 1.469 | 0.758 | -139.886 | False |
| Phthalimide | 0.517 acetone + 0.467 iPrOAc + 0.0167 tBuOAc | 2.724 | 1 acetone | 4.463 | 0.611 | -95.037 | False |
| Succinimide | 0.333 iPrOH + 0.333 iPrOAc + 0.333 tBuOAc | 0.961 | 1 tBuOAc | 0.884 | 1.087 | 2.213 | True |


![report_R1_per_solute](report_R1_per_solute.png)

## R2 the 'dissolves everything' objective

Is there one mixture that dissolves all solutes well at once, i.e. whose worst solute still beats the best single solvent's worst solute? This is the proposal's success criterion.

- Best overall: 0.45 acetone + 0.0333 EtOH + 0.517 iPrOAc (0.774); best pure solvent: 1 acetone (0.406); z = 243.1 -> a mixture beats every single solvent.

| rank | mixture | obj_min_rel | obj_err | worst_solute | n_solvents | first_round |
|---|---|---|---|---|---|---|
| 1 | 0.45 acetone + 0.0333 EtOH + 0.517 iPrOAc | 0.774 | 0.001 | Boc-hydroxyproline | 3 | 2 |
| 2 | 0.467 acetone + 0.0167 EtOH + 0.517 iPrOAc | 0.766 | 0.002 | Boc-hydroxyproline | 3 | 1 |
| 3 | 0.483 acetone + 0.0333 EtOH + 0.483 iPrOAc | 0.765 | 0.001 | Boc-hydroxyproline | 3 | 2 |
| 4 | 0.483 acetone + 0.0167 EtOH + 0.5 iPrOAc | 0.760 | 0.001 | Boc-hydroxyproline | 3 | 2 |
| 5 | 0.5 acetone + 0.0167 EtOH + 0.483 iPrOAc | 0.755 | 0.001 | Boc-hydroxyproline | 3 | 2 |
| 6 | 0.483 acetone + 0.517 iPrOAc | 0.755 | 0.001 | Boc-hydroxyproline | 2 | 2 |
| 7 | 0.5 acetone + 0.5 iPrOAc | 0.752 | 0.001 | Boc-hydroxyproline | 2 | 0 |
| 8 | 0.517 acetone + 0.467 iPrOAc + 0.0167 tBuOAc | 0.748 | 0.001 | Boc-hydroxyproline | 3 | 2 |
| 9 | 0.3 acetone + 0.383 EtOH + 0.317 tBuOAc | 0.746 | 0.001 | Boc-hydroxyproline | 3 | 1 |
| 10 | 0.317 acetone + 0.383 EtOH + 0.3 tBuOAc | 0.745 | 0.001 | Boc-hydroxyproline | 3 | 2 |


![report_R2_objective](report_R2_objective.png)

## R3 BO progress

Is the Bayesian optimisation learning: does the best objective improve round on round, and do its exploit picks outperform its explore picks and the seed grid?

- Exploit picks should sit above explore picks once the model has learnt something; re-tests show cross-round repeatability.

| round | kind | n | mean | best |
|---|---|---|---|---|
| 0 | seed | 23 | 0.441 | 0.751 |
| 1 | exploit | 8 | 0.718 | 0.767 |
| 1 | explore | 6 | 0.384 | 0.430 |
| 1 | retest | 5 | 0.693 | 0.753 |
| 2 | exploit | 8 | 0.756 | 0.774 |
| 2 | explore | 6 | 0.387 | 0.414 |
| 2 | retest | 5 | 0.747 | 0.765 |


![report_R3_progress](report_R3_progress.png)

## R4 composition landscape

Where in composition space do the good mixtures lie, and what does the model believe about the regions it has not measured?

- Ternaries: colour = worst-solute relative solubility; larger points are 3-solvent mixtures. GP panels show the model the BO used.

| trio | n_mixtures |
|---|---|
| acetone / EtOH / tBuOAc | 16 |
| acetone / EtOH / iPrOAc | 11 |
| acetone / EtOH / water | 11 |


![report_R4_ternary](report_R4_ternary.png)

![report_R4_gp](report_R4_gp.png)

![report_R4_binaries](report_R4_binaries.png)

## R5 synergy

Do mixtures dissolve more than the fraction-weighted average of their pure solvents would predict, i.e. is there genuine synergy, and between which solvent pairs?

- Synergy > 0: the mixture dissolves more than the fraction-weighted average of its pure solvents would predict.
- Significant when |z| = |synergy| / its error > 2; the error combines the mixture's and its pure solvents' pooled errors. Typical threshold here: 0.007 in relative solubility (median error 0.003).
- By chance about 5 % of mixtures (2 per solute) pass |z| > 2. Mixtures sharing a pure solvent share its single measurement, so a cluster of same-sign 'significant' synergies around one solvent may just mean that solvent's pure value is off; re-measuring the pure solvents settles it.

| solute | n_mixtures | n_significant | n_significant_positive | mean_synergy | max_synergy | max_z | most_synergistic |
|---|---|---|---|---|---|---|---|
| Boc-hydroxyproline | 45 | 45 | 45 | 0.220 | 0.261 | 202.703 | 0.35 acetone + 0.317 EtOH + 0.333 tBuOAc |
| Glutarimide | 45 | 45 | 45 | 0.154 | 0.205 | 105.481 | 0.517 acetone + 0.467 iPrOAc + 0.0167 tBuOAc |
| Phthalimide | 45 | 45 | 45 | 0.155 | 0.187 | 21.513 | 0.3 acetone + 0.367 EtOH + 0.333 water |
| Succinimide | 45 | 42 | 42 | 0.097 | 0.164 | 6.049 | 0.35 acetone + 0.333 EtOH + 0.317 water |


![report_R5_synergy](report_R5_synergy.png)

## R6 agreement between solutes

Do the solutes prefer the same solvents, or is dissolving all of them a trade-off? Low correlation explains why the worst-solute objective is hard.

- Low or negative correlation means the solutes want different solvents: the worst-solute objective is then a real trade-off.

| solute | Boc-hydroxyproline | Glutarimide | Phthalimide | Succinimide |
|---|---|---|---|---|
| Boc-hydroxyproline | 1.000 | -0.001 | -0.045 | 0.652 |
| Glutarimide | -0.001 | 1.000 | 0.988 | -0.139 |
| Phthalimide | -0.045 | 0.988 | 1.000 | -0.227 |
| Succinimide | 0.652 | -0.139 | -0.227 | 1.000 |


![report_R6_solutes](report_R6_solutes.png)

## R7 dataset

The dataset deliverable: every condition measured on every solute, across rounds, as one picture and the files behind it.

- 61 condition rows over 3 round(s), 4 solutes.
- Deliverable files in the run folder: `bo_dataset.csv`, `bo_dataset_shared.csv`, `plate_map_round0.csv`, `plate_map_round1.csv`, `plate_map_round2.csv`, `results_round0_wells.csv`, `results_round1_wells.csv`, `results_round2_wells.csv`; QC numbers in `qc_summary.md`.

![report_R7_dataset](report_R7_dataset.png)
