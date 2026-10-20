"""QC figures for one round: blank-corrected spectra per solute, and endpoint absorbance per plate."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .spectra import CONTROL_ROLE, N_COLS, ROWS

# Okabe-Ito, one colour per solute; samples are drawn in grey so the control stands out.
OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000"]
SAMPLE_GREY = "#9a9a9a"


def solute_colors(solutes):
    return {s: OKABE_ITO[i % len(OKABE_ITO)] for i, s in enumerate(solutes)}


def plot_spectra(corrected, plate_map, wavelengths, path, nm_range=None):
    """One panel per solute: every well on every plate (grey), DMF controls in colour, picked wavelength dashed."""
    solutes = list(wavelengths.index)
    colors = solute_colors(solutes)
    n = len(solutes)
    ncols = min(n, 2)
    nrows = -(-n // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 3.4 * nrows), squeeze=False, sharex=True)
    for ax, solute in zip(axes.flat, solutes):
        block = plate_map[plate_map["solute"] == solute]
        is_ctrl = block["role"] == CONTROL_ROLE
        for spec in corrected:
            ax.plot(spec.index, spec[block.index[~is_ctrl]].to_numpy(), color=SAMPLE_GREY, lw=0.6, alpha=0.5)
            ax.plot(spec.index, spec[block.index[is_ctrl]].to_numpy(), color=colors[solute], lw=1.4)
        ax.axvline(wavelengths[solute], color=colors[solute], ls="--", lw=1)
        ax.set_title(f"{solute}: read at {wavelengths[solute]:.0f} nm", fontsize=10)
        ax.set_ylabel("Absorbance (blank-corrected)", fontsize=9)
        ax.tick_params(labelsize=8)
        if nm_range:
            ax.set_xlim(*nm_range)
    for ax in axes.flat[n:]:
        ax.axis("off")
    for ax in axes[-1]:
        ax.set_xlabel("Wavelength (nm)", fontsize=9)
    handles = [plt.Line2D([], [], color=SAMPLE_GREY, lw=1, label="Sample wells, all plates"),
               plt.Line2D([], [], color="k", lw=1.4, label="DMF control wells"),
               plt.Line2D([], [], color="k", ls="--", lw=1, label="Picked wavelength")]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8, frameon=False)
    fig.suptitle(f"Round {plate_map['round'].iloc[0]}: spectra per solute", fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_plates(endpoints, plate_map, path, labels=None):
    """8x12 heat map of endpoint absorbance per plate; DMF controls get a white ring (second cue to colour)."""
    labels = labels or [f"Plate {i}" for i in range(1, len(endpoints) + 1)]
    vmax = max(e["absorbance"].max() for e in endpoints)
    vmin = min(0.0, min(e["absorbance"].min() for e in endpoints))
    fig, axes = plt.subplots(1, len(endpoints), figsize=(4.6 * len(endpoints), 3.6), squeeze=False)
    controls = plate_map.index[plate_map["role"] == CONTROL_ROLE]
    for ax, ep, label in zip(axes[0], endpoints, labels):
        grid = np.full((len(ROWS), N_COLS), np.nan)
        for well, a in zip(ep["well"], ep["absorbance"]):
            grid[ROWS.index(well[0]), int(well[1:]) - 1] = a
        im = ax.imshow(grid, cmap="viridis", vmin=vmin, vmax=vmax)
        for well in controls:
            ax.plot(int(well[1:]) - 1, ROWS.index(well[0]), "o", mfc="none", mec="white", mew=1.5, ms=9)
        ax.set_xticks(range(N_COLS), [str(c + 1) for c in range(N_COLS)], fontsize=7)
        ax.set_yticks(range(len(ROWS)), list(ROWS), fontsize=7)
        ax.set_title(label, fontsize=10)
    cbar = fig.colorbar(im, ax=axes[0].tolist(), shrink=0.8, pad=0.02)
    cbar.set_label("Absorbance at solute wavelength", fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    fig.suptitle(f"Round {plate_map['round'].iloc[0]}: endpoint absorbance (ring = DMF control)", fontsize=11)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
