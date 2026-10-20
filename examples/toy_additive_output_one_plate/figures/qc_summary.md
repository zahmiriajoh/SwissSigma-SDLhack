# QC summary: toy_additive_output_one_plate (rounds 1, 2)

## Q1 plate-to-plate reproducibility

How well do the identical plates of a round agree, and is any plate systematically off? The spread sets the noise floor: a mixture must beat the best single solvent by more than this to count.

- Median CV across identical plates is the noise floor a mixture must beat to count as better.
- A plate is flagged when its median deviation from the other plates exceeds 5%.

| round | solute | n_plates | median_cv | flagged_plate |
|---|---|---|---|---|
| 1 | all | 1 |  |  |
| 2 | all | 1 |  |  |


## Q2 control stability

Does the DMF control, the denominator of every relative value, stay constant across plates and rounds? Drift would rescale a whole round and make rounds incomparable.

- Every relative value is divided by its round's control, so control drift between rounds rescales the whole round.
- Drift beyond the within-round CV means a different solid load, evaporation or plate attack.

| solute | round1_mean | max_drift_vs_round1 | within_round_cv |
|---|---|---|---|
| S1 | 1.196 | 0.010 |  |
| S2 | 1.196 | 0.001 |  |
| S3 | 1.205 | 0.013 |  |
| S4 | 1.204 | 0.008 |  |


![qc_Q2_controls](qc_Q2_controls.png)

## Q4 spectral QC

Are any wells saturated, scattering (undissolved solid) or absorbing at the wrong wavelength? Each would inflate or bias that well's solubility without any extra solute dissolving.

- Saturation: raw absorbance above 2.5 (reader linear range placeholder, PLAN Q-b).
- Peak shift needs full spectra and a band of at least 0.05 absorbance (grey = too weak); scattering needs readings at 600-800 nm (add a 700 nm read in fixed-wavelength mode).
- High scattering = undissolved solid in the light path, which inflates that well.

| round | n_saturated | saturated_wells | n_peak_shift_gt10nm | median_abs_peak_shift_nm | max_scatter_abs |
|---|---|---|---|---|---|
| 1 | 0 |  | 0 | 1.000 | 0.001 |
| 2 | 0 |  | 0 | 1.000 | 0.001 |


![qc_Q4_peakshift_round1](qc_Q4_peakshift_round1.png)

![qc_Q4_scatter_round1](qc_Q4_scatter_round1.png)

![qc_Q4_peakshift_round2](qc_Q4_peakshift_round2.png)

![qc_Q4_scatter_round2](qc_Q4_scatter_round2.png)

## Q5 precision against signal

Which conditions are measurable at all, and is the noise constant (reader) or proportional to the signal (pipetting and dissolution)?

- No replicate plates, so there is no within-condition spread to plot; detection limits only.

## Q6 cross-round re-tests

Does a mixture measured again in a later round, on new solid and a new plate, give the same answer? This is the only check that rounds can be pooled.

- Re-tests repeat a mixture on new solid, a new plate and a refilled reservoir: the only check across rounds.
- Grey band: 2 x the median plate-to-plate CV (Q1); frac_within_2cv uses each solute's own CV.

| solute | n_retests | mean_abs_diff | plate_cv | frac_within_2cv |
|---|---|---|---|---|
| S1 | 3 | 0.013 |  |  |
| S2 | 3 | 0.005 |  |  |
| S3 | 3 | 0.010 |  |  |
| S4 | 3 | 0.014 |  |  |


![qc_Q6_retests](qc_Q6_retests.png)
