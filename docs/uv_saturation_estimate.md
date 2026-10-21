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
5. **Solubility, not just absorbance, limits the useful load** (added after reading [6], [7], [9]; see "Solubility data"
   below). No DMF solubility was found for any solute. Phthalimide dissolves only about 6 mg/mL in ethanol and
   isopropanol and about 26 mg/mL in acetone at 25 °C, and succinimide about 42 mg/mL in ethanol and 330 mg/mL in water
   at 20 °C [9], so a load low enough to read undiluted would dissolve fully in these solvents and not tell them apart.

## Caveats

- No spectrum was measured in DMF, and two do not state their solvent. Band positions and intensities shift with solvent.
- If only part of the solid dissolves, the absorbance is lower. That does not change the conclusion for phthalimide.
- The 0–4 OD limit comes from secondary sources [4]; the cap at 4.0 in the code is a separate choice.

## Cross-check and consequences for the analysis

Added 2026-10-21 by the analysis session. The numbers above were recomputed independently from the same ε values and
path length and reproduce. The extra column says how much an aliquot would have to be diluted before reading.

| Solute and wavelength | Highest concentration with A ≤ 4 | Dilution needed from 50 mg/mL | from 400 mg/mL |
|---|---|---|---|
| Phthalimide, 295 nm | 0.33 mg/mL | about 150× | about 1,200× |
| Phthalimide, 320 nm | 4.2 mg/mL | about 12× | about 100× |
| Succinimide, 230 nm | 4.7 mg/mL | about 11× | about 85× |
| Succinimide, 250 nm | 7.6 mg/mL | about 7× | about 50× |

What the analysis pipeline does with these wells today:

1. **The conservative readout cannot rescue this.** `analysis reduce` reads each solute only where every solvent's
   blank stays below absorbance 1.0, moving to a band's shoulder if the maximum is hidden (`analysis/PLAN.md`,
   decision 15). Even phthalimide's weak 320 nm shoulder is 12 to 100 times too strong, so no wavelength choice brings
   the planned loads into range. The fix has to be on the measurement side: dilute an aliquot before reading, load much
   less solid, or use another readout.
2. **Saturated readings pass through unflagged.** The converter turns an over-range cell into 4.0, and `reduce` writes
   `saturated` in the `flag` column of the endpoint files. Nothing downstream reads that flag: `bo_bridge.py merge`,
   `analysis qc` / `report` and SDL_BO all use 4.0 as a real value. A capped DMF control then makes every good solvent
   score about 1.0, and the BO cannot tell them apart.
3. **The `measurable` verdict does not catch it either.** It tests whether the DMF control's signal exceeds 3 times the
   600–700 nm noise. A control capped at 4.0 passes easily, so a saturated solute is reported as measurable.
4. **The 230 nm floor needs no code change.** `reduce` works on whatever wavelength range the export contains, so a
   230–700 nm scan is read as is and the peak search starts at 230 nm. It makes no practical difference here: DMF is
   opaque below about 270 nm and acetone below about 330 nm, so the usable window starts above 230 nm anyway.

Whatever the user decides on dilution or loading, points 2 and 3 suggest a guard: a DMF control above the reader's
linear range should either stop the round or mark that solute not measurable, rather than enter the dataset as 4.0.

## Solubility data: what limits the load

Added 2026-10-21 after reading the two phthalimide solubility papers [6], [7]. The estimates above assume the whole load
dissolves. What a well can actually hold is set by the solute's solubility in that well's solvent, so this section asks
which loads are dissolved, and what a saturated well would read.

### No DMF solubility was found for any solute

Neither paper measures DMF. Xu et al. [6] measured phthalimide in ten solvents; Li et al. [7] measured phthalimide in
mixtures of acetone, ethyl acetate or acetonitrile with methanol. Searches of the NIST WebBook, NIST ThermoML and
PubChem found no measured solubility in DMF for phthalimide, succinimide, glutarimide or Boc-hydroxyproline. PubChem's
phthalimide entry gives only water and hot-ethanol values [8]. **The step-0 DMF pre-test is therefore the only source
of DMF solubility for this campaign.**

### Succinimide in two of our solvents

The *Encyclopedia of Reagents for Organic Synthesis* entry [9] gives succinimide's solubility as 1 g in 3 mL of water
and 1 g in 24 mL of ethanol at 20 °C (1 g in 0.7 mL of water at the boiling point, 1 g in 5 mL of ethanol at 60 °C),
insoluble in ether and chloroform. Per mL of solvent that is about 330 mg/mL in water and about 42 mg/mL in ethanol at
20 °C. It mentions DMF only as a solvent for preparing succinimide's alkali-metal salt, not as a solubility value.

Both are far above the loads that keep succinimide's band below absorbance 4 (4.7 mg/mL at 230 nm, 7.6 mg/mL at
250 nm). A load that low would dissolve fully in water and ethanol and read the same in both, as with phthalimide.

### Phthalimide in three of our green solvents

Xu et al. [6] include acetone, ethanol and isopropanol, three of the six green solvents in `production/config.toml`.
Their mole fractions at 298.15 K (Table 2, relative standard uncertainty 0.02) convert to mg of phthalimide per mL of
solvent with the paper's own molar volumes (Table 1): mg/mL = x / (1 − x) × M(phthalimide) / V(solvent) × 1,000. The
absorbance columns apply the Beer-Lambert estimate above to a saturated well, treating mg per mL of solvent as mg per
mL of solution (volume change on dissolving ignored).

| Solvent | In our campaign | Mole fraction x, 298.15 K [6] | Solubility (mg per mL solvent) | Saturated well: A at 295 nm | A at 320 nm |
|---|---|---|---|---|---|
| Acetone | yes | 0.01278 | about 26 | about 310 | about 25 |
| Ethyl acetate | no (i-PrOAc and t-BuOAc are) | 0.007494 | about 11 | about 130 | about 11 |
| Methanol | no | 0.002604 | about 9.5 | about 110 | about 9 |
| Acetonitrile | no | 0.003048 | about 8.5 | about 100 | about 8 |
| Ethanol | yes | 0.002397 | about 6.0 | about 70 | about 6 |
| Isopropanol | yes | 0.002983 | about 5.7 | about 70 | about 5 |
| Toluene | no | 0.000577 | about 0.8 | about 9 | about 1 |

Solubility rises with temperature in every solvent, by a factor of about 3 to 5 between 283 and 318 K [6], so a lab
below 25 °C dissolves somewhat less. Water was not measured in [6]; PubChem gives 0.36 g/L for water [8], about 0.4 mg/mL.

### What this means for the loading

1. **A 5 mg/mL load does not discriminate phthalimide's solvents.** Acetone, ethanol and isopropanol each dissolve
   at least 5.7 mg/mL, so all three would dissolve the whole load and read the same as DMF (relative value 1.0), as long
   as DMF dissolves it too. Only poorer solvents, such as water, would fall below 1.0.
2. **Separating acetone from the alcohols needs a load above about 26 mg/mL**, acetone's own solubility; separating the
   alcohols from each other needs more than about 6 mg/mL.
3. **Saturated phthalimide wells still overflow the reader.** At 295 nm a saturated ethanol or isopropanol well reads
   about 70 and a saturated acetone well about 310. Even at the 320 nm shoulder the alcohols read 5 to 6 and acetone
   about 25, all above 4. A load that discriminates the solvents therefore cannot be read undiluted at either wavelength.
4. **Mixtures can beat pure solvents.** In acetone + methanol the solubility peaks at an acetone mass fraction of 0.9,
   where x = 0.02045 at 298.15 K against 0.01278 in pure acetone [7], about 1.6 times higher (about 45 mg per mL of solvent).
   This is the kind of non-additive mixture effect the BO is meant to find, and it raises the load needed to see it.
5. **Both papers dilute before measuring.** They filter the saturated solution through a 0.2 µm PTFE filter, dilute
   about 1 mL (or 0.5 mL) to 25 mL, and quantify by HPLC with UV detection at 290 nm [6], [7]. Detection at 290 nm agrees
   with the band used above [1].

### Lower loadings, for comparison

With every load fully dissolved, the same Beer-Lambert estimate gives:

| Solute and wavelength | 5 mg/mL | 10 mg/mL | 20 mg/mL | 50 mg/mL | 100 mg/mL |
|---|---|---|---|---|---|
| Phthalimide, 295 nm | 60 | 119 | 238 | 595 | 1,190 |
| Phthalimide, 310 nm | 14 | 29 | 57 | 144 | 287 |
| Phthalimide, 320 nm | 4.8 | 9.6 | 19 | 48 | 96 |
| Succinimide, 230 nm | 4.2 | 8.5 | 17 | 42 | 85 |
| Succinimide, 250 nm | 2.6 | 5.2 | 10 | 26 | 52 |

At 5 mg/mL only succinimide at 250 nm is below 4, and that band is under DMF's cut-off. Phthalimide at 5 mg/mL drops
below 4 only from about 324 nm, where the database spectrum's tail may be a baseline offset [1].

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
6. Xu, R.; Wang, J.; Han, S.; Du, C.; Meng, L.; Zhao, H. Solubility modelling and thermodynamic dissolution functions of
   phthalimide in ten organic solvents. *J. Chem. Thermodyn.* **2016**, 94, 160–168 (online 2015).
   <https://doi.org/10.1016/j.jct.2015.10.024>. Local copy: `data/papers/`.
7. Li, Y.; Li, C.; Du, C.; Cong, Y.; Cheng, C.; Zhao, H. Solubility determination and modelling for phthalimide in mixed
   solvents of (acetone, ethyl acetate or acetonitrile + methanol) from (278.15 to 313.15) K. *J. Chem. Thermodyn.*
   **2017**, 106, 123–131 (online 2016). <https://doi.org/10.1016/j.jct.2016.11.023>. Corrigendum (model parameters for
   acetonitrile + methanol only; the measured solubilities are unchanged): *J. Chem. Thermodyn.* **2017**, 113, 399,
   <https://doi.org/10.1016/j.jct.2017.07.001>. Local copy: `data/papers/`.
8. PubChem, phthalimide (CID 6809), Solubility, citing the Merck Index (1989) and the Aquasol database (1992):
   <https://pubchem.ncbi.nlm.nih.gov/compound/6809#section=Solubility>.
9. de Koning, H.; Speckamp, W. N. Succinimide. In *Encyclopedia of Reagents for Organic Synthesis*; Wiley, **2001**.
   <https://doi.org/10.1002/047084289X.rs126>. Local copy: `data/papers/`.
