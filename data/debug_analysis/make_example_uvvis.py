"""Generate example UV-Vis plate-reader CSVs (wavelength index, one column per well)."""
from pathlib import Path

import numpy as np
import pandas as pd

WAVELENGTHS = np.arange(200, 801)  # nm, 1 nm steps
WELLS = [f"{r}{c}" for r in "ABCDEFGH" for c in range(1, 13)]  # A1..H12, row-major
OUT_DIR = Path(__file__).parent


def gaussian(x, centre, width):
    return np.exp(-0.5 * ((x - centre) / width) ** 2)


def well_spectrum(rng):
    """Synthetic absorbance: scattering baseline + two chromophore bands + noise."""
    conc = rng.uniform(0.0, 1.0)  # mimics varying kinetic solubility
    baseline = 0.05 + 0.3 * (WAVELENGTHS / 200.0) ** -4  # Rayleigh-like tail into the UV
    bands = 1.2 * gaussian(WAVELENGTHS, 275 + rng.normal(0, 3), 18) + 0.6 * gaussian(
        WAVELENGTHS, 410 + rng.normal(0, 5), 35
    )
    return baseline + conc * bands + rng.normal(0, 0.004, WAVELENGTHS.size)


def make_plate(seed):
    rng = np.random.default_rng(seed)
    data = {well: well_spectrum(rng) for well in WELLS}
    return pd.DataFrame(data, index=pd.Index(WAVELENGTHS, name="wavelength_nm")).round(4)


if __name__ == "__main__":
    for i, seed in enumerate((1, 2), start=1):
        path = OUT_DIR / f"example_uvvis_plate{i}.csv"
        make_plate(seed).to_csv(path)
        print(f"wrote {path}")
