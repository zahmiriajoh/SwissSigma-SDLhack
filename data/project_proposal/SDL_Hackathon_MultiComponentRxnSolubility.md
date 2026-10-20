# High-Throughput Optimization of Green Solvent Systems for Multicomponent PROTAC-like Synthesis via Kinetic Solubility Screening

### Zahmiria Johnson1, Magdalena Lederbauer1, Alex Stoneman1, Bryan Wang1, Mingrou Xie1

1Department of Chemical Engineering, Massachusetts Institute of Technology, Cambridge, USA

**Introduction and Motivation:** Proteolysis targeting chimeras (PROTACs) and other complex heterobifunctional molecules are notoriously difficult to synthesize due to the broad structural diversity of their components (e.g., E3 ligase ligand, target protein ligand, and linker). The amide couplings used to join these fragments are routinely run in N,N-dimethylformamide (DMF) or tetrahydrofuran (THF), which keep all precursors in solution but are hazardous. DMF is a reproductive toxicant whose use is increasingly restricted under EU REACH, and ethereal solvents such as THF raise peroxide-formation and flammability concerns. Replacement is complicated by the fact that no single green solvent reliably dissolves every component of a multicomponent system; in practice, mixtures of greener solvents (for example 2-MeTHF, dimethyl carbonate, CPME, or ethyl acetate) are required to span the necessary solubility range. Identifying these mixtures manually is slow and prone to pipetting error, which limits how much of the compositional space can be explored. A self-driving lab using Bayesian optimization could be a viable platform for discovering green solvent combinations to enable solubility of drug-relevant molecules with reduced cost and expanded discovery space.

**Scientific Question and Hypothesis:** Can an SDL identify green-solvent mixtures that simultaneously dissolve a set of structurally diverse PROTAC building block  proxies, and do so better than any of the constituent solvents alone?

We hypothesise that,a systematic screen, guided by Bayesian optimization, will identify at least one binary or ternary green-solvent mixture in which all three component proxies reach high apparent solubility, outperforming the best single green solvent for each, thereby defining a viable green medium for subsequent heterobifunctional synthesis.

**Success Criteria:**

* Quantitative Metric: At least one specific green solvent mixture, up to three solvents combined, achieves high relative kinetic solubility (measured via UV-Vis absorbance) outperforming the baseline solubility of those components in pure, singular green solvents. An additional evaluation metric is how the best green solvent solubility compares to the standard DMF solubility.  
* Primary Deliverable: A comprehensive, open-access dataset and visualization detailing the relative solubility of the proxy library across a grid of at least 15 different green solvent mixtures as well as DMF solvent (as a standard).

**Analytic Strategy:**

The primary analytical equipment will be a UV-Vis plate reader. To evaluate solubility, a researcher will prepare the solids in the well plate and place it into the Opentrons system. The Opentrons system will then dispense the varying green solvent mixtures into a well plate. After a specified agitation/incubation period, the filtrate's UV-Vis absorbance will be measured; high absorbance indicates high kinetic solubility of the active compounds, while low absorbance indicates precipitation or failure to dissolve.

**Feasibility Assessment:** 

Reagent dispensing, solvent mixing, and plate preparation are standard OT-2 operations. Reaction volumes (200–500 µL) in polypropylene well plates are compatible with the shaker module. The protocol uses solvents that avoid degradation of reaction plates and readout plates. One calibration standard that is prepared during the data collection and a UV-Vis plate reader provide a direct, non-destructive readout with no sample preparation beyond the optional dilution step.

The entire procedure is expected to fit comfortably within a 12-hour window: Round one (\~4 h including setup, reaction, readout), model fitting (\~2 h), round two (\~6 h). 

**Value Addition Argument:**

While there are guides for single green solvent substitutions, datasets mapping the solubility of complex, multicomponent drug-like building blocks in mixtures of green solvents are incredibly scarce. By generating and open-sourcing this dataset, we provide medicinal chemists with a practical, data-driven starting point for transitioning PROTAC and large-molecule syntheses away from toxic solvents. Furthermore, this workflow establishes a reusable self-driving lab (SDL) template: any research group can swap our proxy molecules for their specific proprietary substrates and run the exact same script to find their ideal green reaction environment.

# Description of Experimental Procedure

Reaction liquids/solids: 3x cheap proxy molecules mirroring PROTAC component properties (solid or stock solutions in benign carrier), a library of green solvents (e.g., 2-MeTHF, EtOAc, DMC, CPME, MeCN, i-PrOAc), and a commercially available reference standard for calibration.

Labware: Reservoir for pure solvents, 96-well filter plates (0.22 micron), 96-well PS readout plates (flat bottom).

1. (Manual) Preparation of stock components and placement of deck labware.  
2. (Manual?) Dispense fixed amounts of the proxy molecules (solids) into the initial working plate.  
3. (OT-Flex) Read process parameters (solvent mixture ratios) from a CSV file.  
4. (OT-Flex) Dispense varying ratios of green solvents from the reservoir into the working plate wells.  
5. (OT-Flex) Engage heater-shaker module; agitate all wells at a specified temperature for N minutes to allow for dissolution.  
6. (OT-Flex/Manual?) Filtrate each well into a separate 96-well plate to remove the solids.  
7. (Manual) Transfer the readout plate containing only the solutions to the UV-Vis plate reader.  
8. (Plate reader) Take absorbance measurements to measure solubility; produce CSV output.   
9. (Data) Generate new grid search as a baseline; use Bayesian optimization to select new experiments.   
10. Repeat Steps 2-9. 

# References:

1. Byrne, F. P. et al. “Tools and Techniques for Solvent Selection: Green Solvent Selection Guides”. *Sustain Chem Process* 2016, **4** (1), 7\.  
2. Ferrazzano, L. et al. “Green Solvent Mixtures for Solid-Phase Peptide Synthesis: A Dimethylformamide-Free Highly Efficient Synthesis of Pharmaceutical-Grade Peptides.” *ACS Sustainable Chem. Eng.* 2019, **7** (15), 12867–12877.  
3. Alder, C. M. et al. “Updating and Further Expanding GSK’s Solvent Sustainability Guide”. *Green Chem.* 2016, **18** (13), 3879–3890.  
4. Hoelke B, Gieringer S, Arlt M, Saal C. “Comparison of nephelometric, UV-spectroscopic, and HPLC methods for high-throughput determination of aqueous drug solubility in microtiter plates.” *Anal Chem.* 2009, **1** (8):3165-72.