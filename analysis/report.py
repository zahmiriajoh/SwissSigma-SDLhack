"""The study aims (PLAN.md R1-R7): mixtures vs single solvents, the "dissolves everything" objective, BO progress,
composition landscape, synergy, agreement between solutes and the dataset deliverable. run_report writes report_summary.md.

Relative solubility (`rel`) is absorbance over the same round's DMF control; a mixture measured in several rounds
is pooled (Run.pooled). The objective of a mixture is its worst solute's rel (Run.pooled_objective).
"""
from itertools import combinations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

from .plots import (KIND_STYLE, N_SOLVENT_STYLE, OKABE_ITO, annotated_matrix, barycentric, colors_for, panel_grid,
                    save, ternary_frame)
from .run import KINDS, frac_columns
from .summary import Summary

Z_BETTER = 2.0          # a difference counts as real when it exceeds this many combined standard errors
TOP_N = 10              # mixtures listed per solute / in the parallel-coordinates plot
BINARY_TOL = 0.1        # a binary counts as 50:50 within this fraction
GP_STEP = 0.025         # grid step over a ternary simplex for the GP posterior


def _z(a, a_err, b, b_err):
    return (a - b) / np.sqrt(a_err ** 2 + b_err ** 2 + 1e-12)


def _support(row, solvents):
    return tuple(s for s in solvents if row[f"frac_{s}"] > 0)


# ----- R1 mixtures vs single solvents, per solute --------------------------------------------------

def r1_per_solute(run, outdir):
    pooled = run.pooled()
    colors = colors_for(run.solutes)
    fig, axes = panel_grid(len(run.solutes), 2, (6.2, 4.2))
    rows = []
    for ax, solute in zip(axes, run.solutes):
        p = pooled[pooled["solute"] == solute]
        pure = p[p["n_solvents"] == 1].sort_values("rel")
        mixes = p[p["n_solvents"] > 1].nlargest(TOP_N, "rel").sort_values("rel")
        show = pd.concat([pure, mixes])
        y = np.arange(len(show))
        is_pure = (show["n_solvents"] == 1).to_numpy()
        ax.errorbar(show["rel"][is_pure], y[is_pure], xerr=show["rel_err"][is_pure], fmt="o", color=colors[solute], ms=5, capsize=2, label="Pure solvent")
        ax.errorbar(show["rel"][~is_pure], y[~is_pure], xerr=show["rel_err"][~is_pure], fmt="s", mfc="none", color=colors[solute], ms=5, capsize=2, label=f"Top {TOP_N} mixtures")
        best_pure = pure.iloc[-1] if len(pure) else None
        if best_pure is not None:
            ax.axvline(best_pure["rel"], color=colors[solute], ls="--", lw=0.8, label="Best pure solvent")
        ax.axvline(1.0, color="k", lw=0.8, ls=":", label="DMF")
        ax.set_yticks(y, show["mixture"], fontsize=6.5)
        ax.set_xlabel("Relative solubility (DMF = 1)", fontsize=9)
        ax.set_title(solute + ("  (NOT measurable: values are noise)" if solute in run.unmeasurable else ""), fontsize=10)
        ax.tick_params(axis="x", labelsize=8)
        ax.legend(fontsize=6.5, frameon=False, loc="lower right")
        if len(mixes) and best_pure is not None:
            best_mix = mixes.iloc[-1]
            z = _z(best_mix["rel"], best_mix["rel_err"], best_pure["rel"], best_pure["rel_err"])
            rows.append({"solute": solute, "best_mixture": best_mix["mixture"], "rel_mixture": best_mix["rel"],
                         "best_pure": best_pure["mixture"], "rel_pure": best_pure["rel"],
                         "ratio": best_mix["rel"] / best_pure["rel"], "z": z, "mixture_beats_pure": bool(z > Z_BETTER)})
    fig.suptitle("Pure solvents and the best mixtures per solute", fontsize=11)
    fig.tight_layout()
    notes = [f"z = difference over the combined error (within-plate and between-round spread); a mixture beats the best pure solvent when z > {Z_BETTER:g}."]
    if run.unmeasurable:
        notes.append(f"{run.unmeasurable}: declared not measurable by `analysis reduce` (see wavelengths_roundN.csv); shown for completeness, values are noise.")
    return pd.DataFrame(rows), notes, [save(fig, outdir / "report_R1_per_solute.png")]


# ----- R2 the "dissolves everything" objective ---------------------------------------------------

def r2_objective(run, outdir):
    obj = run.pooled_objective().sort_values("obj_min_rel", ascending=False).reset_index(drop=True)
    pure = obj[obj["n_solvents"] == 1]
    best_pure = pure.iloc[0] if len(pure) else None
    fig, ax = plt.subplots(figsize=(max(6.0, 0.11 * len(obj)), 4))
    for n, (color, hatch) in N_SOLVENT_STYLE.items():
        sel = obj["n_solvents"] == n
        ax.bar(obj.index[sel], obj.loc[sel, "obj_min_rel"], yerr=obj.loc[sel, "obj_err"], color=color, hatch=hatch,
               edgecolor="k", linewidth=0.3, error_kw={"lw": 0.5}, label=f"{n} solvent{'s' if n > 1 else ''}")
    ax.axhline(1.0, color="k", ls=":", lw=0.8, label="DMF")
    if best_pure is not None:
        ax.axhline(best_pure["obj_min_rel"], color="#D55E00", ls="--", lw=0.8, label=f"Best pure: {best_pure['mixture']}")
    ax.set_xlabel("Mixtures ranked by worst-solute relative solubility", fontsize=9)
    ax.set_ylabel("Worst-solute relative solubility", fontsize=9)
    ax.set_xticks([])
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=7, frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    ax.set_title("The 'dissolves everything' objective: every measured mixture", fontsize=11)
    fig.tight_layout()
    rel_cols = [c for c in obj.columns if c.startswith("rel_")]
    obj["worst_solute"] = obj[rel_cols].idxmin(axis=1).str[len("rel_"):]
    single = [f"One solute in this view ({run.measurable_solutes[0]}): the objective is simply its relative solubility."] \
        if len(run.measurable_solutes) == 1 else []
    table = obj.head(TOP_N)[["mixture", "obj_min_rel", "obj_err", "worst_solute", "n_solvents", "first_round"]].copy()
    table.insert(0, "rank", range(1, len(table) + 1))
    notes = [f"Objective over the measurable solutes {run.measurable_solutes}; excluded as NOT measurable by `analysis reduce` "
             f"(control signal within the noise at every usable wavelength): {run.unmeasurable}."] if run.unmeasurable else []
    notes = single + notes
    if best_pure is not None and len(obj):
        best = obj.iloc[0]
        z = _z(best["obj_min_rel"], best["obj_err"], best_pure["obj_min_rel"], best_pure["obj_err"])
        notes.append(f"Best overall: {best['mixture']} ({best['obj_min_rel']:.3f}); best pure solvent: {best_pure['mixture']} "
                     f"({best_pure['obj_min_rel']:.3f}); z = {z:.1f} -> " + ("a mixture beats every single solvent." if best["n_solvents"] > 1 and z > Z_BETTER
                     else "no mixture is clearly better than the best single solvent."))
    return table, notes, [save(fig, outdir / "report_R2_objective.png")]


# ----- R3 BO progress -------------------------------------------------------------------------------

def per_round_objective(run) -> pd.DataFrame:
    """One row per round x condition: obj (min over solutes of rel_mean), kind, mixture."""
    s = run.samples()
    s = s[s["solute"].isin(run.measurable_solutes)]
    g = s.groupby(["round", "condition_id"])
    out = g.agg(obj=("rel_mean", "min"), kind=("kind", "first"), mixture=("mixture", "first"), n_solutes=("solute", "nunique"))
    return out[out["n_solutes"] == len(run.measurable_solutes)].reset_index()


def r3_progress(run, outdir):
    pr = per_round_objective(run)
    best_by_round = pr.groupby("round")["obj"].max()
    incumbent = best_by_round.cummax()
    fig, axes = panel_grid(2, 2, (5, 3.8))
    ax = axes[0]
    ax.step(incumbent.index, incumbent.to_numpy(), where="post", color=OKABE_ITO[0], lw=1.5, label="Best so far")
    ax.plot(best_by_round.index, best_by_round.to_numpy(), "o", color=OKABE_ITO[1], label="Best of the round")
    ax.axhline(best_by_round.iloc[0], color="k", ls="--", lw=0.8, label="Seed-round best")
    ax.axhline(1.0, color="k", ls=":", lw=0.8, label="DMF")
    ax.set_xticks(run.rounds)
    ax.set_xlabel("Round", fontsize=9)
    ax.set_ylabel("Worst-solute relative solubility", fontsize=9)
    ax.set_title("Progress of the objective", fontsize=10)
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    ax = axes[1]
    kinds = [k for k in KINDS if k != "control" and k in set(pr["kind"])]
    rng = np.random.default_rng(0)
    for i, kind in enumerate(kinds):
        color, marker = KIND_STYLE[kind]
        g = pr[pr["kind"] == kind]
        x = g["round"] + (i - (len(kinds) - 1) / 2) * 0.18 + rng.uniform(-0.05, 0.05, len(g))
        ax.plot(x, g["obj"], marker, color=color, ms=4, alpha=0.75, label=kind, mfc="none" if kind == "retest" else color)
    ax.set_xticks(run.rounds)
    ax.set_xlabel("Round", fontsize=9)
    ax.set_ylabel("Worst-solute relative solubility", fontsize=9)
    ax.set_title("Every condition by kind", fontsize=10)
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=7, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1))
    for ax in axes:
        ax.tick_params(labelsize=8)
    fig.suptitle("Bayesian optimisation progress", fontsize=11)
    fig.tight_layout()
    table = pr.groupby(["round", "kind"])["obj"].agg(n="size", mean="mean", best="max").reset_index()
    notes = ["Exploit picks should sit above explore picks once the model has learnt something; re-tests show cross-round repeatability."]
    return table, notes, [save(fig, outdir / "report_R3_progress.png")]


# ----- R4 composition landscape -----------------------------------------------------------------------

def top_trios(run, obj, n=3) -> list:
    """Solvent trios ordered by how many measured mixtures lie inside them (ternaries count 3x, binaries 1x)."""
    counts = {trio: 0 for trio in combinations(run.green_solvents, 3)}
    for _, row in obj.iterrows():
        sup = set(_support(row, run.green_solvents))
        for trio in counts:
            if sup <= set(trio) and len(sup) > 1:
                counts[trio] += 3 if len(sup) == 3 else 1
    return [t for t, c in sorted(counts.items(), key=lambda kv: -kv[1]) if c > 0][:n]


def _in_trio(obj, trio, solvents):
    others = [f"frac_{s}" for s in solvents if s not in trio]
    return obj[(obj[others].sum(axis=1) == 0)] if others else obj


def r4_ternary(run, outdir, obj, trios):
    fig, axes = panel_grid(len(trios), 3, (4.2, 3.9))
    norm = Normalize(vmin=0, vmax=max(1.0, obj["obj_min_rel"].max()))
    for ax, trio in zip(axes, trios):
        pts = _in_trio(obj, trio, run.green_solvents)
        ternary_frame(ax, trio)
        x, y = barycentric(*(pts[f"frac_{s}"] for s in trio))
        sizes = np.where(pts["n_solvents"] == 3, 42, 28)
        ax.scatter(x, y, c=pts["obj_min_rel"], cmap="viridis", norm=norm, s=sizes, edgecolor="k", linewidth=0.4)
        ax.set_title(f"{len(pts)} mixtures measured", fontsize=9)
    fig.colorbar(ScalarMappable(norm=norm, cmap="viridis"), ax=list(axes), shrink=0.8, pad=0.02).set_label("Worst-solute relative solubility", fontsize=9)
    fig.suptitle("Measured mixtures in the most-sampled solvent trios", fontsize=11)
    return save(fig, outdir / "report_R4_ternary.png")


def _simplex_grid(step=GP_STEP):
    a = np.arange(0, 1 + 1e-9, step)
    pts = np.array([(i, j, 1 - i - j) for i in a for j in a if i + j <= 1 + 1e-9])
    return np.clip(pts, 0, 1)


def gp_posteriors(run, seed=0):
    """{solute: FittedModel} from SDL_BO on this run's bo_dataset.csv, plus the solvent order SDL_BO expects."""
    from SDL_BO import space
    from SDL_BO.campaign import fit_per_solute
    from SDL_BO.dataset import load_dataset
    return fit_per_solute(load_dataset(run._optional("bo_dataset.csv")), seed=seed), space.GREEN_SOLVENTS


def r4_gp(run, outdir, trios, seed=0):
    fitted, order = gp_posteriors(run, seed)
    grid3 = _simplex_grid()
    fig, axes = plt.subplots(2, len(trios), figsize=(4.2 * len(trios), 7.4), squeeze=False)
    maps = []
    for trio in trios:
        X = np.zeros((len(grid3), len(order)))
        for k, s in enumerate(trio):
            X[:, order.index(s)] = grid3[:, k]
        means, stds = zip(*(fitted[s].gp.predict(X, return_std=True) for s in run.measurable_solutes if s in fitted))
        maps.append((np.min(means, axis=0), np.mean(stds, axis=0)))
    x, y = barycentric(grid3[:, 0], grid3[:, 1], grid3[:, 2])
    for row, (label, idx, cmap) in enumerate((("GP posterior mean of the objective", 0, "viridis"), ("GP posterior std (mean over solutes)", 1, "cividis"))):
        vmax = max(m[idx].max() for m in maps)
        vmin = min(m[idx].min() for m in maps)
        for ax, trio, m in zip(axes[row], trios, maps):
            cs = ax.tricontourf(x, y, m[idx], levels=np.linspace(vmin, vmax, 13), cmap=cmap)
            ternary_frame(ax, trio)
        cbar = fig.colorbar(cs, ax=axes[row].tolist(), shrink=0.85, pad=0.02, format="%.2f" if idx == 0 else "%.3f")
        cbar.set_label(label, fontsize=9)
        cbar.ax.tick_params(labelsize=8)
    fig.suptitle("Gaussian-process belief over the same trios (SDL_BO models)", fontsize=11)
    return save(fig, outdir / "report_R4_gp.png")


def r4_binaries(run, outdir, obj):
    sv = run.green_solvents
    m = np.full((len(sv), len(sv)), np.nan)
    for _, row in obj.iterrows():
        sup = _support(row, sv)
        if len(sup) == 1:
            i = sv.index(sup[0])
            m[i, i] = np.nanmax([m[i, i], row["obj_min_rel"]])
        elif len(sup) == 2 and abs(row[f"frac_{sup[0]}"] - 0.5) <= BINARY_TOL:
            i, j = sorted(sv.index(s) for s in sup)
            m[i, j] = np.nanmean([m[i, j], row["obj_min_rel"]])
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    im = annotated_matrix(ax, m, sv, "viridis", vmin=0, vmax=max(1.0, np.nanmax(m)))
    fig.colorbar(im, ax=ax, shrink=0.8).set_label("Worst-solute relative solubility", fontsize=9)
    ax.set_title("Pure solvents (diagonal) and 50:50 binaries", fontsize=11)
    fig.tight_layout()
    return save(fig, outdir / "report_R4_binaries.png")


def r4_landscape(run, outdir, with_gp=True, seed=0):
    obj = run.pooled_objective()
    trios = top_trios(run, obj)
    figs, notes = [], []
    if trios:
        figs.append(r4_ternary(run, outdir, obj, trios))
        if with_gp:
            try:
                figs.append(r4_gp(run, outdir, trios, seed))
            except Exception as error:  # SDL_BO missing or too little data: the rest of the report still stands
                notes.append(f"GP posterior skipped: {error}")
    else:
        notes.append("No binary or ternary mixtures measured yet, so no ternary plots.")
    figs.append(r4_binaries(run, outdir, obj))
    table = pd.DataFrame({"trio": [" / ".join(t) for t in trios], "n_mixtures": [len(_in_trio(obj, t, run.green_solvents)) for t in trios]})
    notes.append("Ternaries: colour = worst-solute relative solubility; larger points are 3-solvent mixtures. GP panels show the model the BO used.")
    return table, notes, figs


# ----- R5 synergy ----------------------------------------------------------------------------------------

def synergy_table(run) -> pd.DataFrame:
    """Per solute x mixture: rel minus the fraction-weighted rel of its pure solvents (linear mixing rule), its error,
    z = synergy / error and `significant` (|z| > Z_BETTER)."""
    p = run.pooled()
    sv = run.green_solvents
    pure = {(r["solute"], _support(r, sv)[0]): (r["rel"], r["rel_err"]) for _, r in p[p["n_solvents"] == 1].iterrows()}
    rows = []
    for _, r in p[p["n_solvents"] > 1].iterrows():
        sup = _support(r, sv)
        if all((r["solute"], s) in pure for s in sup):
            linear = sum(r[f"frac_{s}"] * pure[(r["solute"], s)][0] for s in sup)
            err = np.sqrt(r["rel_err"] ** 2 + sum((r[f"frac_{s}"] * pure[(r["solute"], s)][1]) ** 2 for s in sup) + 1e-12)
            rows.append({"solute": r["solute"], "mixture": r["mixture"], "support": sup, "n_solvents": r["n_solvents"],
                         "balance": 1 - sum(r[f"frac_{s}"] ** 2 for s in sup), "rel": r["rel"], "linear": linear,
                         "synergy": r["rel"] - linear, "synergy_err": err})
    syn = pd.DataFrame(rows)
    if len(syn):
        syn["z"] = syn["synergy"] / syn["synergy_err"]
        syn["significant"] = syn["z"].abs() > Z_BETTER
    return syn


def r5_synergy(run, outdir):
    syn = synergy_table(run)
    if syn.empty:
        return pd.DataFrame(), ["No mixture has all its pure solvents measured, so synergy cannot be computed."], []
    colors = colors_for(run.solutes)
    sv = run.green_solvents
    fig, axes = panel_grid(2, 2, (5.2, 4.2))
    ax = axes[0]
    for solute in run.solutes:
        g = syn[syn["solute"] == solute]
        for n, marker in ((2, "o"), (3, "^")):
            for sig, fill in ((True, colors[solute]), (False, "none")):  # filled = significant, open = within noise
                gg = g[(g["n_solvents"] == n) & (g["significant"] == sig)]
                ax.plot(gg["balance"], gg["synergy"], marker, color=colors[solute], mfc=fill, ms=4, alpha=0.8, label=f"{solute}, {n} solvents")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xlabel("Mixture balance, 1 - sum of squared fractions", fontsize=9)
    ax.set_ylabel("Synergy: measured minus linear mixing", fontsize=9)
    ax.set_title(f"Per mixture and solute (filled = |z| > {Z_BETTER:g})", fontsize=10)
    handles, labels = ax.get_legend_handles_labels()
    seen = {}
    for label, handle in zip(labels, handles):  # one entry per solute and size, showing the filled (significant) marker
        seen.setdefault(label, handle)
    ax.legend(seen.values(), seen.keys(), fontsize=6, frameon=False, ncol=2)
    m = np.full((len(sv), len(sv)), np.nan)
    for i, j in combinations(range(len(sv)), 2):
        vals = syn[[sv[i] in s and sv[j] in s for s in syn["support"]]]["synergy"]
        if len(vals):
            m[i, j] = vals.mean()
    lim = np.nanmax(np.abs(m)) if np.isfinite(m).any() else 0.1
    im = annotated_matrix(axes[1], m, sv, "PuOr", fmt="{:+.3f}", vmin=-lim, vmax=lim)
    fig.colorbar(im, ax=axes[1], shrink=0.8).set_label("Mean synergy of mixtures with both solvents", fontsize=9)
    axes[1].set_title("Per solvent pair (all solutes)", fontsize=10)
    for ax in axes:
        ax.tick_params(labelsize=8)
    fig.suptitle("Synergy relative to the linear mixing rule", fontsize=11)
    fig.tight_layout()
    table = syn.groupby("solute").agg(n_mixtures=("synergy", "size"), n_significant=("significant", "sum"),
                                      n_significant_positive=("z", lambda z: int((z > Z_BETTER).sum())),
                                      mean_synergy=("synergy", "mean"), max_synergy=("synergy", "max"),
                                      max_z=("z", lambda z: float(z.loc[syn.loc[z.index, "synergy"].idxmax()])),
                                      most_synergistic=("synergy", lambda s: syn.loc[s.idxmax(), "mixture"])).reset_index()
    typical = float(syn["synergy_err"].median())
    notes = ["Synergy > 0: the mixture dissolves more than the fraction-weighted average of its pure solvents would predict.",
             f"Significant when |z| = |synergy| / its error > {Z_BETTER:g}; the error combines the mixture's and its pure solvents' pooled errors. "
             f"Typical threshold here: {Z_BETTER * typical:.3f} in relative solubility (median error {typical:.3f}).",
             f"By chance about 5 % of mixtures ({0.05 * len(syn) / max(len(run.solutes), 1):.0f} per solute) pass |z| > {Z_BETTER:g}. "
             "Mixtures sharing a pure solvent share its single measurement, so a cluster of same-sign 'significant' synergies "
             "around one solvent may just mean that solvent's pure value is off; re-measuring the pure solvents settles it."]
    return table, notes, [save(fig, outdir / "report_R5_synergy.png")]


# ----- R6 do the solutes agree? ---------------------------------------------------------------------------

def r6_solute_agreement(run, outdir):
    solutes = run.measurable_solutes
    if len(solutes) < 2:  # e.g. a one-solute arm: nothing to compare
        return pd.DataFrame(), [f"Only {len(solutes)} measurable solute in this view ({', '.join(solutes)}): nothing to compare."], []
    obj = run.pooled_objective()
    rel = obj[[f"rel_{s}" for s in solutes]].rename(columns=lambda c: c[len("rel_"):])
    corr = rel.corr()
    fig, axes = panel_grid(2, 2, (5.2, 4.2))
    im = annotated_matrix(axes[0], corr.to_numpy(), solutes, "cividis", vmin=-1, vmax=1)
    fig.colorbar(im, ax=axes[0], shrink=0.8).set_label("Pearson correlation across mixtures", fontsize=9)
    axes[0].set_title("Do solutes prefer the same mixtures?", fontsize=10)
    ax = axes[1]
    top = obj.nlargest(TOP_N, "obj_min_rel")
    cmap = plt.get_cmap("viridis")
    for k, (_, row) in enumerate(top.iterrows()):
        ax.plot(range(len(solutes)), [row[f"rel_{s}"] for s in solutes], "o-", ms=3, lw=1,
                color=cmap(1 - k / max(len(top) - 1, 1)), label=f"{k + 1}. {row['mixture']}")
    ax.axhline(1.0, color="k", ls=":", lw=0.8)
    ax.set_xticks(range(len(solutes)), solutes)
    ax.set_ylabel("Relative solubility", fontsize=9)
    ax.set_title(f"Top {TOP_N} mixtures across solutes", fontsize=10)
    ax.legend(fontsize=6, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    for ax in axes:
        ax.tick_params(labelsize=8)
    fig.suptitle("Agreement between solutes", fontsize=11)
    fig.tight_layout()
    table = corr.round(3).reset_index().rename(columns={"index": "solute"})
    notes = ["Low or negative correlation means the solutes want different solvents: the worst-solute objective is then a real trade-off."]
    return table, notes, [save(fig, outdir / "report_R6_solutes.png")]


# ----- R7 deliverable dataset ---------------------------------------------------------------------------------

def r7_dataset(run, outdir):
    s = run.samples().sort_values(["round", "condition_id"])
    wide = s.pivot_table(index=["round", "condition_id", "mixture"], columns="solute", values="rel_mean")[run.solutes]
    wide["worst"] = wide.min(axis=1)
    fig, ax = plt.subplots(figsize=(6.5, max(4.0, 0.13 * len(wide) + 1)))
    im = ax.imshow(wide.to_numpy(), cmap="viridis", aspect="auto", vmin=0, vmax=max(1.0, np.nanmax(wide.to_numpy())))
    ax.set_xticks(range(wide.shape[1]), list(wide.columns), fontsize=8, rotation=30, ha="right", rotation_mode="anchor")
    ax.set_yticks(range(len(wide)), [f"R{r} {c}  {m}" for r, c, m in wide.index], fontsize=5)
    rounds = wide.index.get_level_values("round").to_numpy()
    for k in np.where(np.diff(rounds) != 0)[0]:
        ax.axhline(k + 0.5, color="white", lw=1.5)
    ax.axvline(wide.shape[1] - 1.5, color="white", lw=1.5)
    fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02).set_label("Relative solubility (DMF = 1)", fontsize=9)
    ax.set_title("All conditions by solute, grouped by round", fontsize=11)
    fig.tight_layout()
    files = ["bo_dataset.csv", "bo_dataset_shared.csv"] + [f"plate_map_round{r}.csv" for r in run.rounds] + [f"results_round{r}_wells.csv" for r in run.rounds]
    notes = [f"{len(wide)} condition rows over {len(run.rounds)} round(s), {len(run.solutes)} solute(s).",
             "Deliverable files in the run folder: " + ", ".join(f"`{f}`" for f in files if run._optional(f)) + "; QC numbers in the `qc_summary.md` written by `analysis qc` (one level up with `--arms`)."]
    return pd.DataFrame(), notes, [save(fig, outdir / "report_R7_dataset.png")]


# ----- driver ------------------------------------------------------------------------------------------------

QUESTIONS = {  # what each analysis is for, printed under its heading in report_summary.md
    "R1": "For each solute on its own, does any green-solvent mixture dissolve more than the best single green solvent, "
          "and how close does it come to DMF?",
    "R2": "Is there one mixture that dissolves all solutes in this report well at once (with `--arms`: that arm's solutes), "
          "i.e. whose worst solute still beats the best single solvent's worst solute? This is the proposal's success criterion.",
    "R3": "Is the Bayesian optimisation learning: does the best objective improve round on round, and do its exploit picks "
          "outperform its explore picks and the seed grid?",
    "R4": "Where in composition space do the good mixtures lie, and what does the model believe about the regions it has "
          "not measured?",
    "R5": "Do mixtures dissolve more than the fraction-weighted average of their pure solvents would predict, "
          "i.e. is there genuine synergy, and between which solvent pairs?",
    "R6": "Do the solutes prefer the same solvents, or is dissolving all of them a trade-off? "
          "Low correlation explains why the worst-solute objective is hard.",
    "R7": "The dataset deliverable: every condition measured on every solute, across rounds, as one picture and the files "
          "behind it.",
}


def run_report(run, outdir, with_gp=True, seed=0, arm=None):
    """All R1-R7 sections into outdir/report_summary.md; `arm` names the arm whose solutes `run` was restricted to."""
    outdir.mkdir(parents=True, exist_ok=True)
    view = f", arm {arm}: {', '.join(run.solutes)}" if arm else ""
    summary = Summary(f"Report: {run.folder.name} (rounds {', '.join(map(str, run.rounds))}{view})")
    parts = [("R1 mixtures vs single solvents, per solute", r1_per_solute(run, outdir)),
             ("R2 the 'dissolves everything' objective", r2_objective(run, outdir)),
             ("R3 BO progress", r3_progress(run, outdir)),
             ("R4 composition landscape", r4_landscape(run, outdir, with_gp, seed)),
             ("R5 synergy", r5_synergy(run, outdir)),
             ("R6 agreement between solutes", r6_solute_agreement(run, outdir)),
             ("R7 dataset", r7_dataset(run, outdir))]
    for title, (table, notes, figs) in parts:
        summary.section(title, notes, table, figs, QUESTIONS[title.split()[0]])
    return summary.write(outdir / "report_summary.md")
