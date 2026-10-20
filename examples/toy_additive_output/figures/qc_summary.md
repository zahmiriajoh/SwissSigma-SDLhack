# QC summary: toy_additive_output (rounds 1, 2, 3)

## Q1 plate-to-plate reproducibility

- Median CV across identical plates is the noise floor a mixture must beat to count as better.
- A plate is flagged when its median deviation from the other plates exceeds 5%.

| round | solute | n_plates | median_cv | flagged_plate |
|---|---|---|---|---|
| 1 | S1 | 3 | 0.007 |  |
| 1 | S2 | 3 | 0.005 |  |
| 1 | S3 | 3 | 0.005 |  |
| 1 | S4 | 3 | 0.005 |  |
| 2 | S1 | 3 | 0.004 |  |
| 2 | S2 | 3 | 0.004 |  |
| 2 | S3 | 3 | 0.005 |  |
| 2 | S4 | 3 | 0.004 |  |
| 3 | S1 | 3 | 0.004 |  |
| 3 | S2 | 3 | 0.006 |  |
| 3 | S3 | 3 | 0.005 |  |
| 3 | S4 | 3 | 0.006 |  |


![qc_Q1_plates_round1](qc_Q1_plates_round1.png)

![qc_Q1_plates_round2](qc_Q1_plates_round2.png)

![qc_Q1_plates_round3](qc_Q1_plates_round3.png)

## Q2 control stability

- Every relative value is divided by its round's control, so control drift between rounds rescales the whole round.
- Drift beyond the within-round CV means a different solid load, evaporation or plate attack.

| solute | round1_mean | max_drift_vs_round1 | within_round_cv |
|---|---|---|---|
| S1 | 1.200 | 0.006 | 0.003 |
| S2 | 1.192 | 0.012 | 0.003 |
| S3 | 1.192 | 0.006 | 0.002 |
| S4 | 1.197 | 0.006 | 0.002 |


![qc_Q2_controls](qc_Q2_controls.png)

## Q3 blank wells and plate attack

- b_<solvent>: blank absorbance of the pure solvent at that solute's wavelength (additive fit over all blank wells).
- Low R^2 or large residuals mean the blank is not additive in composition, i.e. plate attack or solvent interaction.
- Read-delay panel appears only when plate_log_roundN.csv files exist.

| solute | b_DMF | b_2MeTHF | b_EtOAc | b_DMC | b_CPME | b_MeCN | b_iPrOAc | resid_std | r2 |
|---|---|---|---|---|---|---|---|---|---|
| S1 | 0.131 | 0.134 | 0.133 | 0.133 | 0.136 | 0.128 | 0.136 | 0.003 | 0.165 |
| S2 | 0.095 | 0.095 | 0.095 | 0.095 | 0.098 | 0.095 | 0.095 | 0.004 | 0.016 |
| S3 | 0.083 | 0.083 | 0.085 | 0.082 | 0.082 | 0.083 | 0.082 | 0.003 | 0.050 |
| S4 | 0.071 | 0.066 | 0.067 | 0.068 | 0.072 | 0.070 | 0.067 | 0.004 | 0.076 |


![qc_Q3_blank](qc_Q3_blank.png)

## Q4 spectral QC

- Saturation: raw absorbance above 2.5 (reader linear range placeholder, PLAN Q-b).
- Peak shift needs full spectra and a band of at least 0.05 absorbance (grey = too weak); scattering needs readings at 600-800 nm (add a 700 nm read in fixed-wavelength mode).
- High scattering = undissolved solid in the light path, which inflates that well.

| round | n_saturated | saturated_wells | n_peak_shift_gt10nm | median_abs_peak_shift_nm | max_scatter_abs |
|---|---|---|---|---|---|
| 1 | 0 |  | 0 | 1.000 | 0.001 |
| 2 | 0 |  | 0 | 1.000 | 0.001 |
| 3 | 0 |  | 0 | 1.000 | 0.001 |


![qc_Q4_peakshift_round1](qc_Q4_peakshift_round1.png)

![qc_Q4_scatter_round1](qc_Q4_scatter_round1.png)

![qc_Q4_peakshift_round2](qc_Q4_peakshift_round2.png)

![qc_Q4_scatter_round2](qc_Q4_scatter_round2.png)

![qc_Q4_peakshift_round3](qc_Q4_peakshift_round3.png)

![qc_Q4_scatter_round3](qc_Q4_scatter_round3.png)

## Q5 precision against signal

- Detection limit = 3 x residual std of the blank model (Q3).
- log slope near 0: constant (reader) noise; near 1: proportional (pipetting/dissolution) noise.

| solute | detection_limit_abs | frac_below_lod | log_slope_std_vs_mean |
|---|---|---|---|
| S1 | 0.010 | 0.000 | -0.208 |
| S2 | 0.013 | 0.000 | -0.118 |
| S3 | 0.010 | 0.000 | 0.116 |
| S4 | 0.011 | 0.000 | -0.642 |


![qc_Q5_precision](qc_Q5_precision.png)

## Q6 cross-round re-tests

- Re-tests repeat a mixture on new solid, a new plate and a refilled reservoir: the only check across rounds.
- Grey band: 2 x the median plate-to-plate CV (Q1); frac_within_2cv uses each solute's own CV.

| solute | n_retests | mean_abs_diff | plate_cv | frac_within_2cv |
|---|---|---|---|---|
| S1 | 6 | 0.004 | 0.004 | 0.833 |
| S2 | 6 | 0.005 | 0.005 | 0.833 |
| S3 | 6 | 0.004 | 0.005 | 0.833 |
| S4 | 6 | 0.006 | 0.005 | 0.500 |


![qc_Q6_retests](qc_Q6_retests.png)

## Q7 calibration

- No QC plate (qc_plate_map_roundN.csv + reader_roundN_qc.csv) found.
