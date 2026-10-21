# Will the UV-Vis readout saturate? An estimate from published spectra

Written 2026-10-21 for the production campaign in `production/config.toml`. Nothing here has been measured on our
plate reader: every number is a Beer-Lambert estimate from literature spectra. The direct check is a plate-reader
scan of the step-0 DMF pre-test wells (Scientist instructions, section B, step 0).

## Question

The Scientist instructions load each well with the highest concentration from a DMF pre-test at 50, 100, 200 and
400 mg/mL, and the plates are read undiluted. Every relative value divides a well's absorbance by its solute's DMF
control. If that control reads above the reader's range, `production/convert_reader_xlsx.py` caps it at absorbance
4.0 (the `OVER` cell), nothing downstream treats the capped value differently, and the relative values lose their meaning.

## Method

Absorbance A = ε · c · l (Beer-Lambert), assuming the whole load dissolves.

| Quantity | Value | Source |
|---|---|---|
| Path length l | 0.88 cm = 300 µL / (π × (0.33 cm)²) | well diameter 6.6 mm in `OT protocols/labware/sarstedt_96_wellplate_390ul_flatbottom.json`; 300 µL per well in `production/config.toml` |
| Concentration c | 50 and 400 mg/mL, divided by the molar mass | loadings from the Scientist instructions; molar masses: phthalimide 147.13, succinimide 99.09, glutarimide 113.11, Boc-hydroxyproline 231.25 g/mol [5] |
| Molar absorptivity ε | per solute and wavelength, below | [1]–[3] |
| Reader limit | absorbance 4 | 0–4 OD in reseller specifications and a Tecan assay guide [4] |

## Published spectra

| Solute | Spectrum | Solvent | Data range | ε in the reader's range (M⁻¹cm⁻¹) |
|---|---|---|---|---|
| Phthalimide | PhotochemCAD E07 [1] | ethanol | 200–800 nm | 1,680 at 280 nm; 2,090 at 290 nm; 2,000 at 295 nm; 1,870 at 300 nm; 480 at 310 nm; 160 at 320 nm |
| Succinimide | NIST WebBook, Saidel 1953 [2] | not stated | 201–259 nm | 96 at 230 nm; 88 at 240 nm; 59 at 250 nm; 7 at 259 nm |
| Glutarimide | NIST WebBook, Turner and Wheeler 1957 [3] | not stated | 179–207 nm | no data above 207 nm (log ε 3.92 at 207 nm) |
| Boc-hydroxyproline | none found | | | no data |

Phthalimide's strongest band is at 215 nm (ε 44,100 [1]), below the reader's range. Its ε stays near 100 from 330 to
350 nm without falling, which looks like a baseline offset in the database spectrum rather than real absorption, so
those values are not used.

## Estimated absorbances

| Solute and wavelength | A at 50 mg/mL | A at 400 mg/mL | Highest concentration with A ≤ 4 |
|---|---|---|---|
| Phthalimide, 295 nm | about 600 | about 4,800 | 0.34 mg/mL (2.3 mM) |
| Phthalimide, 300 nm | about 560 | about 4,500 | 0.36 mg/mL (2.4 mM) |
| Phthalimide, 320 nm | about 50 | about 380 | 4.2 mg/mL (28 mM) |
| Succinimide, 230 nm | about 40 | about 340 | 4.7 mg/mL (47 mM) |
| Succinimide, 250 nm | about 26 | about 210 | 7.6 mg/mL (77 mM) |

## Findings

1. **Phthalimide and succinimide would saturate at every planned loading**, by roughly 10 to 1,000 times. Staying
   below absorbance 4 needs a few mg/mL or less, so roughly 10 to 100 times dilution from the planned loads, or a much
   smaller solid load.
2. **Succinimide's only band in range is hidden by DMF.** It lies at 230–250 nm, where DMF is opaque, so the DMF control
   cannot show it whatever the loading.
3. **Glutarimide and Boc-hydroxyproline cannot be estimated.** No data were found above 207 nm. Their structures
   (cyclic imide; carbamate and carboxylic acid) suggest little or no absorption above 230 nm, but that is chemical
   reasoning, not a measurement.
4. **The reader may not scan below 230 nm.** Reseller specifications give the Tecan Infinite 200 PRO's absorbance
   wavelength range as 230–1,000 nm [4], while the plan and the Scientist instructions scan 200–700 nm. Tecan's own
   datasheet was not found; confirm on the instrument.

## Caveats

- No spectrum was measured in DMF, and two do not state their solvent. Band positions and intensities shift with solvent.
- If only part of the solid dissolves, the absorbance is lower. That does not change the conclusion for phthalimide.
- The 0–4 OD limit comes from secondary sources [4]; the cap at 4.0 in the code is a separate choice.

## References

1. Taniguchi, M.; Lindsey, J. S. Database of absorption and fluorescence spectra of >300 common compounds for use in
   PhotochemCAD. *Photochem. Photobiol.* **2018**, 94, 290–327. Phthalimide (E07), ethanol:
   <https://www.photochemcad.com/databases/common-compounds/heterocycles/phthalimide>; data file
   <https://www.photochemcad.com/downloads/databases/common-compounds/E07/E07.absorption.txt>.
2. Saidel, L. J. Contribution of the ultra-violet absorption spectrum of asparagine to the problem of its structure.
   *Nature* **1953**, 955–956. Succinimide ("succinic acid imide") UV/Vis spectrum, NIST Chemistry WebBook, CAS 123-56-8:
   <https://webbook.nist.gov/cgi/cbook.cgi?ID=C123568&Mask=400>.
3. Turner, D. W.; Wheeler, R. B. *J. Chem. Soc.* **1957**, 4555. Glutarimide UV/Vis spectrum, NIST Chemistry WebBook,
   CAS 1121-89-7: <https://webbook.nist.gov/cgi/cbook.cgi?ID=C1121897&Mask=400>.
4. Tecan Infinite 200 PRO specifications as listed by a reseller (0–4 OD, 230–1,000 nm):
   <https://newlifescientific.com/products/tecan-infinite-m200-pro-microplate-reader-30050303-with-pc-and-magellan>;
   Tecan assay guide (0–4 OD dynamic range):
   <https://www.cnsi.ucsb.edu/sites/default/files/2022-02/tecan_assayguide_customer_version.pdf>.
5. Molar masses: Boc-hydroxyproline (CAS 13726-69-7) 231.25 g/mol from the supplier listing
   <https://www.thermofisher.com/order/catalog/product/H27110.06>; phthalimide, succinimide and glutarimide computed from
   their formulas (C₈H₅NO₂, C₄H₅NO₂, C₅H₇NO₂).
