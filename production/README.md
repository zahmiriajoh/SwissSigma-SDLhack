# production

**The one place the real experiment is defined.** `config.toml` holds the solutes, solvents, reservoir troughs,
volumes and numbering convention for the production campaign; `config.py` reads and validates it and exposes the
values as constants for the rest of the repo. Change the experiment here, not in the modules.

```python
from production.config import SOLUTES, ALL_SOLVENTS, GREEN_SOLVENTS, REFERENCE_SOLVENT, SOLVENT_TROUGHS, \
    PLATE_ATTACKERS, TOTAL_UL, MIN_UL, N_PLATES, FIRST_ROUND, FIRST_PLATE, FIRST_CONDITION
```

Standard library only (`tomllib`, Python 3.11+), so `OT protocols/bo_bridge.py` can load it as well. The OT-2
protocol itself runs on the robot and cannot import the repo: its `SOLVENT_TROUGHS` must be edited by hand to match,
and the test suite checks that it does.

## What is in `config.toml` (as of 2026-10-20)

| Section | Values | Notes |
|---|---|---|
| `numbering` | first round 0, first plate 0, first condition 0 | "numbering for everything starts from zero"; well names stay A1–H12 |
| `well` | 300 µL per well, 5 µL minimum component, up to 3 solvents | the control well is 300 µL of pure DMF |
| `plates` | 3 identical plates per round; 25 mL trough fill, 1 mL dead volume | plus one QC plate per round (`analysis qc-layout`) |
| `reference` | DMF | pure control in every solute block, never mixed |
| `solutes` | Glutarimide, Boc-hydroxyproline, Phthalimide, Succinimide | plate-block order; add `wavelength_nm` once the absorption maximum is known (absent = pick from data) |
| `solvents` | DMF (A1), acetone (B1), EtOH (C1), i-PrOH (D1), water (E1), i-PrOAc (F1), t-BuOAc (G1) | `name` without hyphens is the CSV identifier, `label` the display name; H1 stays the diluent |

`attacks_polystyrene` marks the solvents expected to craze the polystyrene readout plate (acetone and the esters);
`analysis qc` uses it for the plate-attack check.

## Interpretation notes for the user to confirm

- "Each well: 300 µL of DMF" was read as **300 µL total liquid per well**, with the reference control being 300 µL of
  pure DMF. If instead every well should contain DMF, the mixture model changes and this file is wrong.
- Zero-based numbering was applied to rounds, plates and condition counters (`round0`, `plate0`, `R0_seed00`), not to
  well names.
- **UV readout concern.** DMF is opaque below about 270 nm and acetone below about 330 nm, while glutarimide,
  succinimide and Boc-hydroxyproline have little absorbance above about 250 nm; only phthalimide (about 295 nm) has a
  comfortable band. A UV absorbance readout of the other three solutes, especially in acetone-containing mixtures, may
  not be measurable. Please check the solutes' spectra and the solvent cut-offs before the first run.
- **Immiscible pairs.** Water is immiscible with i-PrOAc and t-BuOAc, so the seed grid and the BO will propose
  water/ester mixtures that phase-separate unless those pairs are forbidden. Nothing in the pipeline forbids them yet;
  say whether they should be excluded (raised by sdl_merge as well).

## Who reads it

| Consumer | What it takes |
|---|---|
| `OT protocols/bo_bridge.py` | solvents, solutes, troughs, volumes, numbering (sdl_merge wiring) |
| `OT protocols/sdl_solubility_ot2.py` | `SOLVENT_TROUGHS` mirrored by hand; checked by `tests/` |
| `SDL_BO/` | solvents, number of solutes, volumes, trough budget, first round (sdl_merge wiring) |
| `analysis/` | reference solvent, polystyrene attackers, solvent labels |
| `tests/test_production_config.py` | that the file is consistent |
