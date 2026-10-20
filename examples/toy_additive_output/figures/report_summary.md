# Report: toy_additive_output (rounds 1, 2, 3)

## R1 mixtures vs single solvents, per solute

- z = difference over the combined error (within-plate and between-round spread); a mixture beats the best pure solvent when z > 2.

| solute | best_mixture | rel_mixture | best_pure | rel_pure | ratio | z | mixture_beats_pure |
|---|---|---|---|---|---|---|---|
| S1 | 0.983 DMC + 0.0167 iPrOAc | 0.896 | 1 DMC | 0.897 | 0.998 | -0.420 | False |
| S2 | 0.983 DMC + 0.0167 MeCN | 0.897 | 1 DMC | 0.900 | 0.997 | -0.344 | False |
| S3 | 0.0167 2MeTHF + 0.983 DMC | 0.899 | 1 DMC | 0.902 | 0.997 | -0.661 | False |
| S4 | 0.0167 2MeTHF + 0.983 DMC | 0.905 | 1 DMC | 0.903 | 1.003 | 0.240 | False |

Figure: `report_R1_per_solute.png`

## R2 the 'dissolves everything' objective

- Best overall: 1 DMC (0.897); best pure solvent: 1 DMC (0.897); z = 0.0 -> no mixture is clearly better than the best single solvent.

| rank | mixture | obj_min_rel | obj_err | worst_solute | n_solvents | first_round |
|---|---|---|---|---|---|---|
| 1 | 1 DMC | 0.897 | 0.004 | S1 | 1 | 1 |
| 2 | 0.983 DMC + 0.0167 iPrOAc | 0.890 | 0.002 | S2 | 2 | 2 |
| 3 | 0.983 DMC + 0.0167 MeCN | 0.889 | 0.002 | S1 | 2 | 2 |
| 4 | 0.0167 2MeTHF + 0.983 DMC | 0.886 | 0.002 | S1 | 2 | 3 |
| 5 | 0.983 DMC + 0.0167 CPME | 0.883 | 0.005 | S4 | 2 | 2 |
| 6 | 0.0167 EtOAc + 0.983 DMC | 0.883 | 0.003 | S1 | 2 | 2 |
| 7 | 0.0167 EtOAc + 0.967 DMC + 0.0167 MeCN | 0.882 | 0.004 | S3 | 3 | 3 |
| 8 | 0.0167 EtOAc + 0.967 DMC + 0.0167 iPrOAc | 0.876 | 0.003 | S2 | 3 | 3 |
| 9 | 0.217 EtOAc + 0.65 DMC + 0.133 MeCN | 0.739 | 0.002 | S3 | 3 | 3 |
| 10 | 0.333 EtOAc + 0.667 DMC | 0.712 | 0.011 | S1 | 2 | 1 |

Figure: `report_R2_objective.png`

## R3 BO progress

- Exploit picks should sit above explore picks once the model has learnt something; re-tests show cross-round repeatability.

| round | kind | n | mean | best |
|---|---|---|---|---|
| 1 | seed | 23 | 0.417 | 0.900 |
| 2 | exploit | 12 | 0.616 | 0.889 |
| 2 | explore | 8 | 0.345 | 0.409 |
| 2 | retest | 3 | 0.754 | 0.894 |
| 3 | exploit | 12 | 0.593 | 0.886 |
| 3 | explore | 8 | 0.334 | 0.435 |
| 3 | retest | 3 | 0.890 | 0.891 |

Figure: `report_R3_progress.png`

## R4 composition landscape

- Ternaries: colour = worst-solute relative solubility; larger points are 3-solvent mixtures. GP panels show the model the BO used.

| trio | n_mixtures |
|---|---|
| EtOAc / CPME / iPrOAc | 17 |
| 2MeTHF / EtOAc / iPrOAc | 13 |
| EtOAc / DMC / MeCN | 13 |

Figure: `report_R4_ternary.png`
Figure: `report_R4_gp.png`
Figure: `report_R4_binaries.png`

## R5 synergy

- Synergy > 0: the mixture dissolves more than the fraction-weighted average of its pure solvents would predict.

| solute | n_mixtures | mean_synergy | max_synergy | most_synergistic |
|---|---|---|---|---|
| S1 | 57 | -0.000 | 0.009 | 0.667 2MeTHF + 0.333 DMC |
| S2 | 57 | -0.003 | 0.008 | 0.5 DMC + 0.5 MeCN |
| S3 | 57 | -0.004 | 0.004 | 0.0167 2MeTHF + 0.983 DMC |
| S4 | 57 | -0.001 | 0.011 | 0.5 DMC + 0.5 iPrOAc |

Figure: `report_R5_synergy.png`

## R6 agreement between solutes

- Low or negative correlation means the solutes want different solvents: the worst-solute objective is then a real trade-off.

| solute | S1 | S2 | S3 | S4 |
|---|---|---|---|---|
| S1 | 1.000 | 0.774 | 0.645 | 0.616 |
| S2 | 0.774 | 1.000 | 0.748 | 0.642 |
| S3 | 0.645 | 0.748 | 1.000 | 0.714 |
| S4 | 0.616 | 0.642 | 0.714 | 1.000 |

Figure: `report_R6_solutes.png`

## R7 dataset

- 69 condition rows over 3 round(s), 4 solutes.
- Deliverable files in the run folder: `bo_dataset.csv`, `bo_dataset_shared.csv`, `plate_map_round1.csv`, `plate_map_round2.csv`, `plate_map_round3.csv`, `results_round1_wells.csv`, `results_round2_wells.csv`, `results_round3_wells.csv`; QC numbers in `qc_summary.md`.
Figure: `report_R7_dataset.png`
