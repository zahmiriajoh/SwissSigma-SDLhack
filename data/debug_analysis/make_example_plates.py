"""Generate example plate maps and matching synthetic UV-Vis CSVs for two 96-well plates.

Design (per plate, one proxy molecule per well):
  60 wells: 20 solvent mixtures x 3 proxies
  18 wells: 6 pure green solvents x 3 proxies (single-solvent baselines)
   3 wells: DMF reference x 3 proxies
   7 wells: solvent-only blanks (6 green + DMF)
   8 wells: calibration-standard dilution series in DMF
Plate 1 = initial grid (equal-part binaries and ternaries); plate 2 = mock BO round 2.
"""
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).parent
WAVELENGTHS = np.arange(200, 801)  # nm, 1 nm steps
WELLS = [f"{r}{c}" for r in "ABCDEFGH" for c in range(1, 13)]  # A1..H12, row-major
GREEN = ["2-MeTHF", "EtOAc", "DMC", "CPME", "MeCN", "i-PrOAc"]
SOLVENTS = GREEN + ["DMF"]
PROXIES = ["proxy_A", "proxy_B", "proxy_C"]
TOTAL_VOLUME_UL = 300
CALIBRATION_MM = np.linspace(0.125, 1.0, 8)  # standard concentrations, mM

# Fake "dissolving power" of each solvent for each proxy (0-1), DMF dissolves everything.
POWER = pd.DataFrame(
    [[0.7, 0.3, 0.5], [0.4, 0.6, 0.3], [0.6, 0.5, 0.4], [0.5, 0.2, 0.7], [0.3, 0.7, 0.6], [0.4, 0.4, 0.3], [1, 1, 1]],
    index=SOLVENTS, columns=PROXIES,
)
# Absorption band (centre nm, width nm) of each proxy and of the calibration standard.
BANDS = {"proxy_A": (275, 18), "proxy_B": (320, 22), "proxy_C": (410, 35), "standard": (350, 25)}


def grid_mixtures():
    """Plate 1: 15 equal-part binaries + 5 equal-part ternaries of the green solvents."""
    binaries = [{a: 0.5, b: 0.5} for a, b in combinations(GREEN, 2)]
    ternaries = [{s: 1 / 3 for s in trio} for trio in list(combinations(GREEN, 3))[::4][:5]]
    return binaries + ternaries


def bo_mixtures(rng, n=20):
    """Plate 2: denser 2-3 component mixtures in 5 % steps, as if proposed by BO."""
    mixtures = []
    while len(mixtures) < n:
        comps = rng.choice(GREEN, size=rng.integers(2, 4), replace=False)
        fracs = np.round(rng.dirichlet(np.ones(len(comps))) * 20) / 20
        mix = {s: f for s, f in zip(comps, fracs) if f > 0}
        if len(mix) >= 2 and abs(sum(mix.values()) - 1) < 1e-9 and mix not in mixtures:
            mixtures.append(mix)
    return mixtures


def plate_map(mixtures):
    """Assign roles and compositions to wells in row-major order."""
    rows = []
    for i, mix in enumerate(mixtures, start=1):
        rows += [dict(role="mixture", mixture_id=f"M{i:02d}", proxy=p, **mix) for p in PROXIES]
    for s in GREEN:
        rows += [dict(role="pure_solvent", mixture_id=s, proxy=p, **{s: 1.0}) for p in PROXIES]
    rows += [dict(role="dmf_reference", mixture_id="DMF", proxy=p, DMF=1.0) for p in PROXIES]
    rows += [dict(role="blank", mixture_id=s, proxy="none", **{s: 1.0}) for s in SOLVENTS]
    rows += [dict(role="calibration", mixture_id="DMF", proxy="standard", DMF=1.0, standard_conc_mM=c) for c in CALIBRATION_MM]
    df = pd.DataFrame(rows, index=pd.Index(WELLS, name="well")).fillna({s: 0.0 for s in SOLVENTS})
    cols = ["role", "mixture_id", "proxy"] + [f"frac_{s}" for s in SOLVENTS] + ["total_volume_ul", "standard_conc_mM"]
    df = df.rename(columns={s: f"frac_{s}" for s in SOLVENTS}).assign(total_volume_ul=TOTAL_VOLUME_UL)
    return df.reindex(columns=cols).round(3)


def gaussian(x, centre, width):
    return np.exp(-0.5 * ((x - centre) / width) ** 2)


def dissolved_fraction(row):
    """Fake kinetic solubility: fraction-weighted power plus a synergy bonus for mixtures."""
    fracs = np.array([row[f"frac_{s}"] for s in SOLVENTS])
    base = fracs @ POWER[row["proxy"]].values
    synergy = 0.4 * (1 - np.sum(fracs**2))  # 0 for pure solvents, larger for balanced mixtures
    return min(base + synergy, 1.0)


def well_spectrum(row, rng):
    """Baseline + analyte band scaled by amount dissolved + noise."""
    baseline = 0.05 + 0.3 * (WAVELENGTHS / 200.0) ** -4
    amount = 0.0
    if row["proxy"] in PROXIES:
        amount = 1.2 * dissolved_fraction(row)
    elif row["proxy"] == "standard":
        amount = 1.5 * row["standard_conc_mM"]
    centre, width = BANDS.get(row["proxy"], (0, 1))
    return baseline + amount * gaussian(WAVELENGTHS, centre, width) + rng.normal(0, 0.004, WAVELENGTHS.size)


def spectra(pmap, rng):
    data = {well: well_spectrum(row, rng) for well, row in pmap.iterrows()}
    return pd.DataFrame(data, index=pd.Index(WAVELENGTHS, name="wavelength_nm")).round(4)


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    for i, mixtures in enumerate((grid_mixtures(), bo_mixtures(rng)), start=1):
        pmap = plate_map(mixtures)
        pmap.to_csv(OUT_DIR / f"example_platemap_plate{i}.csv")
        spectra(pmap, rng).to_csv(OUT_DIR / f"example_uvvis_plate{i}.csv")
        print(f"plate {i}: {pmap['role'].value_counts().to_dict()}")
