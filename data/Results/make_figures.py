"""Figures and turbidity table for data/Results/analysis_summary.md, from Magdalena.xlsx (round 0).

    PYTHONPATH=. uv run python data/Results/make_figures.py      # from the repo root; writes data/Results/figures/
"""
from pathlib import Path
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from production.convert_reader_xlsx import _block, _reading

HERE = Path(__file__).parent
OUT = HERE / "figures"


def load_sheets(path) -> dict:
    """{sheet name: long table (well, wavelength_nm, absorbance)}, OVER read as 4.0 as in the pipeline."""
    out = {}
    for name, grid in pd.read_excel(path, sheet_name=None, header=None).items():
        grid.columns = range(grid.shape[1])
        df = pd.DataFrame(_block(grid), columns=["well", "wavelength_nm", "absorbance"])
        out[name] = df.assign(absorbance=df.absorbance.map(_reading))
    return out


SHEETS = load_sheets(HERE / "Magdalena.xlsx")
OKABE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000"]
SOLUTES = ["Glutarimide", "Boc-hydroxyproline", "Phthalimide", "Succinimide"]
SOL_COL = dict(zip(SOLUTES, OKABE))
SOLVENTS = ["DMF", "acetone", "EtOH", "iPrOH", "water", "iPrOAc", "tBuOAc"]
LABEL = {"DMF": "DMF", "acetone": "acetone", "EtOH": "EtOH", "iPrOH": "i-PrOH", "water": "water", "iPrOAc": "i-PrOAc", "tBuOAc": "t-BuOAc"}
SOLV_COL = {"DMF": "#000000", "acetone": "#E69F00", "EtOH": "#0072B2", "iPrOH": "#56B4E9", "water": "#009E73", "iPrOAc": "#D55E00", "tBuOAc": "#CC79A7"}
SOLV_LS = {"DMF": "-", "acetone": "-", "EtOH": "-", "iPrOH": "--", "water": "-", "iPrOAc": "-", "tBuOAc": "--"}
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.alpha": 0.25, "savefig.dpi": 300})

pm = pd.read_csv("production/csvs/ratios/plate_map_round0.csv")
def mix(r):
    if r.frac_DMF > 0: return "DMF"
    return " / ".join(f"{LABEL[s]} {int(round(r['frac_' + s] * 100))}" for s in SOLVENTS[1:] if r["frac_" + s] > 0)
pm["mix"] = pm.apply(mix, axis=1)

plates = pd.concat([SHEETS[f"plate{p}"].assign(plate=p) for p in range(3)])
plates = plates.merge(pm[["well", "solute", "cond", "mix"]], on="well")
blank = SHEETS["Reader_roundN_solvents.xlsx"].pivot(index="wavelength_nm", columns="well", values="absorbance")
full = SHEETS["solvent_round0_fullplate"]

# --- Fig 1: solvent blank spectra on the polystyrene plate
fig, ax = plt.subplots(figsize=(6.5, 3.6))
for w, name in zip([f"{r}1" for r in "ABCDEFG"], SOLVENTS):
    ax.plot(blank.index, blank[w], color=SOLV_COL[name], ls=SOLV_LS[name], lw=1.5, label=LABEL[name])
ax.plot(blank.index, blank["H1"], color="0.5", ls=":", lw=1.5, label="H1, empty well")
ax.axhline(1.0, color="0.3", lw=0.8, ls="-.")
ax.text(690, 1.08, "Blank limit used by analysis reduce (1.0)", ha="right", va="bottom", fontsize=7, color="0.3")
ax.axhline(4.0, color="0.3", lw=0.8, ls=":")
ax.text(690, 4.2, "Reader cap (OVER = 4.0)", ha="right", va="bottom", fontsize=7, color="0.3")
ax.set_yscale("log"); ax.set_ylim(0.03, 6); ax.set_xlim(230, 700)
ax.set_xlabel("Wavelength (nm)"); ax.set_ylabel("Absorbance (log scale)")
ax.set_title("Round 0 solvent blank plate, column 1 (300 µL pure solvent, Sarstedt polystyrene)")
ax.legend(ncol=8, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False)
fig.tight_layout(); fig.savefig(f"{OUT}/fig1_blank_spectra.png", bbox_inches="tight"); plt.close(fig)

# --- Fig 2: turbidity (mean 600-700 nm) heat maps
def grid(df, col):
    g = df.copy(); g["r"] = g.well.str[0]; g["c"] = g.well.str[1:].astype(int)
    return g.pivot(index="r", columns="c", values=col).reindex(list("ABCDEFGH"))
turb = plates[plates.wavelength_nm >= 600].groupby(["well", "plate"]).absorbance.mean().reset_index()
fturb = full[full.wavelength_nm >= 600].groupby("well").absorbance.mean().reset_index()
fig, axes = plt.subplots(1, 4, figsize=(11, 3.1), sharey=True)
titles = [f"Sample plate {p}" for p in range(3)] + ["Blank plate, full read (only A1-G1 filled)"]
grids = [grid(turb[turb.plate == p], "absorbance") for p in range(3)] + [grid(fturb, "absorbance")]
for ax, g, t in zip(axes, grids, titles):
    im = ax.imshow(g.to_numpy(), cmap="viridis", vmin=0, vmax=2.4, aspect="equal")
    ax.set_xticks(range(12)); ax.set_xticklabels(range(1, 13), fontsize=6.5)
    ax.set_yticks(range(8)); ax.set_yticklabels(list("ABCDEFGH"), fontsize=6.5)
    ax.set_title(t, fontsize=8); ax.grid(False)
    for k in (1.5, 3.5, 5.5): ax.axhline(k, color="white", lw=0.8)
for i, s in enumerate(SOLUTES):
    axes[0].text(-1.6, 2 * i + 0.5, s, ha="right", va="center", fontsize=6.5, color=SOL_COL[s], fontweight="bold")
cb = fig.colorbar(im, ax=axes, fraction=0.015, pad=0.03); cb.set_label("Mean absorbance 600-700 nm", fontsize=7)
fig.suptitle("Turbidity map: absorbance where no solute or solvent absorbs (rows A-B, C-D, E-F, G-H = solute blocks; column 1 = DMF control)", fontsize=8.5, y=0.99)
fig.savefig(f"{OUT}/fig2_turbidity_heatmaps.png", bbox_inches="tight"); plt.close(fig)

# --- Fig 3: turbidity per condition and solute, plates as markers
tc = plates[plates.wavelength_nm >= 600].groupby(["solute", "cond", "mix", "plate"]).absorbance.mean().unstack("plate")
tc["mean"] = tc.mean(axis=1); tc["sd"] = tc[[0, 1, 2]].std(axis=1)
tc.reset_index().to_csv(f"{OUT}/turbidity_600_700nm.csv", index=False, float_format="%.3f")
order = pm[pm.solute == SOLUTES[0]].sort_values("cond").mix.tolist()
markers = ["o", "s", "^"]
fig, axes = plt.subplots(1, 4, figsize=(11, 5.2), sharey=True)
for ax, s in zip(axes, SOLUTES):
    d = tc.loc[s].reset_index().set_index("mix").loc[order]
    y = np.arange(len(order))
    ax.barh(y, d["mean"], color=SOL_COL[s], alpha=0.35, height=0.7)
    for p, m in enumerate(markers):
        ax.scatter(d[p], y, marker=m, s=14, color=SOL_COL[s], edgecolor="black", linewidth=0.4, label=f"plate {p}", zorder=3)
    ax.axvline(0.3, color="0.3", lw=0.8, ls="--")
    ax.set_title(s, color=SOL_COL[s], fontsize=9); ax.set_xlim(0, 2.5); ax.set_xlabel("Mean absorbance 600-700 nm")
    ax.invert_yaxis() if ax is axes[0] else None
axes[0].set_yticks(np.arange(len(order))); axes[0].set_yticklabels(order, fontsize=7)
h, l = axes[0].get_legend_handles_labels()
h.append(Line2D([], [], color="0.3", lw=0.8, ls="--")); l.append("0.3, taken as clear")
fig.legend(h, l, loc="lower center", ncol=4, fontsize=7.5, frameon=False, bbox_to_anchor=(0.6, 0.0))
fig.suptitle("Turbidity per condition (bar = mean of 3 plates; same order in every panel; 15 mg solid in 300 µL = 50 mg/mL)", fontsize=9)
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(f"{OUT}/fig3_turbidity_by_condition.png"); plt.close(fig)

# --- Fig 4: pure-solvent spectra per solute (mean over plates)
pure = pm[(pm.cond <= 6)][["well", "solute", "cond"]]
spec = plates.merge(pure[["well"]], on="well").groupby(["solute", "cond", "wavelength_nm"]).absorbance.mean().unstack("wavelength_nm")
fig, axes = plt.subplots(2, 2, figsize=(9, 6), sharex=True, sharey=True)
for ax, s in zip(axes.ravel(), SOLUTES):
    for c, name in enumerate(SOLVENTS):
        row = spec.loc[(s, c)]
        ax.plot(row.index, row.to_numpy(), color=SOLV_COL[name], ls=SOLV_LS[name], lw=1.4, label=LABEL[name])
    ax.plot(blank.index, blank["H1"], color="0.5", ls=":", lw=1.2, label="empty well")
    ax.axhline(4.0, color="0.3", lw=0.7, ls=":")
    ax.set_title(s, color=SOL_COL[s], fontsize=9); ax.set_yscale("log"); ax.set_ylim(0.03, 6); ax.set_xlim(230, 700)
for ax in axes[1]: ax.set_xlabel("Wavelength (nm)")
for ax in axes[:, 0]: ax.set_ylabel("Absorbance (log scale)")
h, l = axes[0, 0].get_legend_handles_labels()
fig.legend(h, l, ncol=8, fontsize=7.5, frameon=False, loc="lower center")
fig.suptitle("Spectra of the pure-solvent wells per solute (mean of 3 plates; flat 4.0 = over range)", fontsize=9)
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(f"{OUT}/fig4_pure_solvent_spectra.png"); plt.close(fig)

# --- numbers for the summary
over = plates[plates.absorbance >= 4.0]
print("OVER cells per plate, total / above 290 nm:")
print(pd.DataFrame({"total": over.groupby("plate").size(), "above_290": over[over.wavelength_nm > 290].groupby("plate").size()}))
print("\nOVER cells above 290 nm by solute:"); print(over[over.wavelength_nm > 290].groupby("solute").size())
clear = tc[tc["mean"] < 0.3]; print(f"\nclear conditions (mean A600-700 < 0.3): {len(clear)} of {len(tc)}")
print(clear[["mean", "sd"]].round(2).to_string())
print("\nmedian plate-to-plate sd of A600-700 per solute:"); print(tc.groupby("solute")["sd"].median().round(3))
print("\nblank plate drift between the two reads (second - first), 700 nm and 300 nm:")
b2 = full.pivot(index="wavelength_nm", columns="well", values="absorbance")
for w in [f"{r}1" for r in "ABCDEFGH"]:
    print(w, round(b2.loc[700, w] - blank.loc[700, w], 3), round(b2.loc[300, w] - blank.loc[300, w], 3))
