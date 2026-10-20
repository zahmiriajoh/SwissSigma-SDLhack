"""Shared plotting helpers and the `reduce` QC figures (spectra per solute, endpoint plate maps)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .spectra import CONTROL_ROLE, N_COLS, ROWS

DPI = 300
# Okabe-Ito: one colour per solute everywhere; solvents and condition kinds use the same list with a marker cue.
OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000"]
SAMPLE_GREY = "#9a9a9a"
KIND_STYLE = {  # condition kinds: colour + marker (second cue)
    "seed": ("#0072B2", "o"), "exploit": ("#D55E00", "^"), "explore": ("#009E73", "s"),
    "retest": ("#CC79A7", "D"), "control": ("#000000", "x"),
}
N_SOLVENT_STYLE = {1: ("#56B4E9", ""), 2: ("#E69F00", "//"), 3: ("#009E73", "xx")}  # colour + hatch
PLATE_MARKERS = ["o", "s", "^", "D", "v"]


def colors_for(names) -> dict:
    return {n: OKABE_ITO[i % len(OKABE_ITO)] for i, n in enumerate(names)}


def save(fig, path):
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def panel_grid(n, ncols=2, size=(5.0, 3.4), **kw):
    """Axes for n panels, extra panels switched off."""
    ncols = min(n, ncols)
    nrows = -(-n // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(size[0] * ncols, size[1] * nrows), squeeze=False, **kw)
    for ax in axes.flat[n:]:
        ax.axis("off")
    return fig, axes.flat[:n]


def well_grid(values) -> np.ndarray:
    """{well: value} or Series indexed by well -> 8x12 array (NaN where empty)."""
    grid = np.full((len(ROWS), N_COLS), np.nan)
    for well, v in dict(values).items():
        grid[ROWS.index(well[0]), int(well[1:]) - 1] = v
    return grid


def plate_heatmap(ax, values, title, cmap="viridis", vmin=None, vmax=None, ring_wells=(), fontsize=7):
    """One 8x12 plate as an image; ring_wells get a white ring (second cue to colour)."""
    im = ax.imshow(well_grid(values), cmap=cmap, vmin=vmin, vmax=vmax)
    for well in ring_wells:
        ax.plot(int(well[1:]) - 1, ROWS.index(well[0]), "o", mfc="none", mec="white", mew=1.5, ms=9)
    ax.set_xticks(range(N_COLS), [str(c + 1) for c in range(N_COLS)], fontsize=fontsize)
    ax.set_yticks(range(len(ROWS)), list(ROWS), fontsize=fontsize)
    ax.set_title(title, fontsize=10)
    return im


def identity_line(ax, color="k"):
    lo, hi = ax.get_xlim(), ax.get_ylim()
    lim = (min(lo[0], hi[0]), max(lo[1], hi[1]))
    ax.plot(lim, lim, color=color, lw=0.8, ls=":")
    ax.set_xlim(lim)
    ax.set_ylim(lim)


def barycentric(fa, fb, fc):
    """Fractions of corner solvents a (left), b (right), c (top) -> x, y in a unit-side triangle."""
    fa, fb, fc = (np.asarray(f, float) for f in (fa, fb, fc))
    return fb + 0.5 * fc, (np.sqrt(3) / 2) * fc


def ternary_frame(ax, labels, fontsize=8):
    """Draw the triangle and corner labels; hide the cartesian axes."""
    xs, ys = barycentric([1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0])
    ax.plot(xs, ys, color="k", lw=0.8)
    for (x, y), lab, (dx, dy) in zip(zip(*barycentric([1, 0, 0], [0, 1, 0], [0, 0, 1])), labels, [(-0.02, -0.04), (0.02, -0.04), (0, 0.03)]):
        ax.text(x + dx, y + dy, lab, ha="center", va="center", fontsize=fontsize)
    ax.set_aspect("equal")
    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(-0.1, 0.98)
    ax.axis("off")


def annotated_matrix(ax, matrix, labels, cmap, fmt="{:.2f}", fontsize=7, vmin=None, vmax=None):
    """Square heat map with the value written in every cell (text colour flips on dark cells)."""
    m = np.asarray(matrix, float)
    im = ax.imshow(m, cmap=cmap, vmin=vmin, vmax=vmax)
    norm = im.norm
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            if not np.isnan(m[i, j]):
                dark = norm(m[i, j]) < 0.5
                ax.text(j, i, fmt.format(m[i, j]), ha="center", va="center", fontsize=fontsize, color="white" if dark else "black")
    ax.set_xticks(range(len(labels)), labels, fontsize=fontsize, rotation=30, ha="right")
    ax.set_yticks(range(len(labels)), labels, fontsize=fontsize)
    return im


# ----- figures of the `reduce` step --------------------------------------------------------------

def plot_spectra(corrected, plate_map, wavelengths, path, nm_range=None):
    """One panel per solute: every well on every plate (grey), DMF controls in colour, picked wavelength dashed."""
    solutes = list(wavelengths.index)
    colors = colors_for(solutes)
    fig, axes = panel_grid(len(solutes), 2, (5.2, 3.4), sharex=True)
    for ax, solute in zip(axes, solutes):
        block = plate_map[plate_map["solute"] == solute]
        is_ctrl = block["role"] == CONTROL_ROLE
        for spec in corrected:
            ax.plot(spec.index, spec[block.index[~is_ctrl]].to_numpy(), color=SAMPLE_GREY, lw=0.6, alpha=0.5)
            ax.plot(spec.index, spec[block.index[is_ctrl]].to_numpy(), color=colors[solute], lw=1.4)
        ax.axvline(wavelengths[solute], color=colors[solute], ls="--", lw=1)
        ax.set_title(f"{solute}: read at {wavelengths[solute]:.0f} nm", fontsize=10)
        ax.set_ylabel("Absorbance (blank-corrected)", fontsize=9)
        ax.set_xlabel("Wavelength (nm)", fontsize=9)
        ax.tick_params(labelsize=8)
        if nm_range:
            ax.set_xlim(*nm_range)
    handles = [plt.Line2D([], [], color=SAMPLE_GREY, lw=1, label="Sample wells, all plates"),
               plt.Line2D([], [], color="k", lw=1.4, label="DMF control wells"),
               plt.Line2D([], [], color="k", ls="--", lw=1, label="Picked wavelength")]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8, frameon=False)
    fig.suptitle(f"Round {plate_map['round'].iloc[0]}: spectra per solute", fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    return save(fig, path)


def plot_plates(endpoints, plate_map, path, labels=None):
    """8x12 heat map of endpoint absorbance per plate; DMF controls ringed."""
    labels = labels or [f"Plate {i}" for i in range(1, len(endpoints) + 1)]
    vmax = max(e["absorbance"].max() for e in endpoints)
    vmin = min(0.0, min(e["absorbance"].min() for e in endpoints))
    fig, axes = plt.subplots(1, len(endpoints), figsize=(4.6 * len(endpoints), 3.6), squeeze=False)
    controls = plate_map.index[plate_map["role"] == CONTROL_ROLE]
    for ax, ep, label in zip(axes[0], endpoints, labels):
        im = plate_heatmap(ax, dict(zip(ep["well"], ep["absorbance"])), label, vmin=vmin, vmax=vmax, ring_wells=controls)
    cbar = fig.colorbar(im, ax=axes[0].tolist(), shrink=0.8, pad=0.02)
    cbar.set_label("Absorbance at solute wavelength", fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    fig.suptitle(f"Round {plate_map['round'].iloc[0]}: endpoint absorbance (ring = DMF control)", fontsize=11)
    return save(fig, path)
