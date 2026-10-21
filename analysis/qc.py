"""Experiment quality (PLAN.md Q1, Q2, Q4-Q6; Q3 blanks and Q7 calibration were dropped with the QC plate): reproducibility,
control drift, spectra, precision and re-tests. Each check returns (summary table, notes, figure paths); run_qc writes qc_summary.md.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .plots import (PLATE_MARKERS, colors_for, identity_line, panel_grid, plate_heatmap, save)
from .spectra import ABS_MAX_DEFAULT, DEFAULT_NM_RANGE, MIN_SIGNAL_SIGMAS, blank_correct
from .summary import Summary

PLATE_OFFSET_FLAG = 0.05       # a plate whose median deviates from the others by more than this is flagged
SCATTER_NM = (600.0, 700.0)    # no solute absorbs here (top of the 200-700 nm scan): signal = scattering by undissolved solid
MIN_ABS_FOR_PEAK = 0.05     # peak position is only meaningful for wells whose corrected band is at least this high


# ----- Q1 plate-to-plate reproducibility ----------------------------------------------------------

def q1_plate_reproducibility(run, outdir):
    rows, figs = [], []
    colors = colors_for(run.solutes)
    for r in run.rounds:
        w = run.wells[(run.wells["round"] == r)]
        wide = w.pivot_table(index=["solute", "well"], columns="plate", values="abs_corrected")
        plates = list(wide.columns)
        if len(plates) < 2:
            rows.append({"round": r, "solute": "all", "n_plates": 1, "median_cv": np.nan, "flagged_plate": ""})
            continue
        cv = (wide.std(axis=1) / wide.mean(axis=1)).rename("cv")
        others = {p: wide.drop(columns=p).mean(axis=1) for p in plates}
        offsets = {p: float(((wide[p] - others[p]) / others[p]).median()) for p in plates}
        flagged = [str(p) for p, o in offsets.items() if abs(o) > PLATE_OFFSET_FLAG]
        for solute in run.solutes:
            rows.append({"round": r, "solute": solute, "n_plates": len(plates),
                         "median_cv": float(cv.loc[solute].median()), "flagged_plate": ",".join(flagged)})
        fig, axes = panel_grid(len(run.solutes) + 1, len(run.solutes) + 1, (3.3, 3.2))
        for ax, solute in zip(axes, run.solutes):
            for k, p in enumerate(plates[1:], start=1):
                ax.plot(wide.loc[solute, plates[0]], wide.loc[solute, p], PLATE_MARKERS[k], ms=4, alpha=0.7,
                        color=colors[solute], mfc="none" if k > 1 else colors[solute], label=f"Plate {p}")
            identity_line(ax)
            ax.set_title(f"{solute}: CV {cv.loc[solute].median():.1%}", fontsize=10)
            ax.set_xlabel(f"Plate {plates[0]} absorbance", fontsize=9)
            ax.set_ylabel("Other plate absorbance", fontsize=9)
            ax.tick_params(labelsize=8)
            ax.legend(fontsize=7, frameon=False)
        ax = axes[-1]
        ax.hist([cv.loc[s].to_numpy() * 100 for s in run.solutes], bins=20, stacked=True,
                color=[colors[s] for s in run.solutes], label=run.solutes)
        ax.set_xlabel("CV across plates (%)", fontsize=9)
        ax.set_ylabel("Wells", fontsize=9)
        ax.set_title("Spread per condition", fontsize=10)
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=7, frameon=False)
        fig.suptitle(f"Round {r}: plate-to-plate reproducibility" + (f" (offset plate(s): {', '.join(flagged)})" if flagged else ""), fontsize=11)
        fig.tight_layout()
        figs.append(save(fig, outdir / f"qc_Q1_plates_round{r}.png"))
    table = pd.DataFrame(rows)
    notes = ["Median CV across identical plates is the noise floor a mixture must beat to count as better.",
             f"A plate is flagged when its median deviation from the other plates exceeds {PLATE_OFFSET_FLAG:.0%}."]
    return table, notes, figs


# ----- Q2 control stability -------------------------------------------------------------------------

def q2_control_stability(run, outdir):
    ctrl = run.wells[run.wells["role"] == "control"]
    colors = colors_for(run.solutes)
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    rows = []
    for solute in run.solutes:
        c = ctrl[ctrl["solute"] == solute]
        by_round = c.groupby("round")["abs_corrected"].mean()
        for k, (p, g) in enumerate(c.groupby("plate")):
            ax.plot(g["round"], g["abs_corrected"], PLATE_MARKERS[k % len(PLATE_MARKERS)], color=colors[solute],
                    ms=5, alpha=0.8, mfc="none" if k else colors[solute])
        ax.plot(by_round.index, by_round.to_numpy(), "-", color=colors[solute], lw=1.2, label=solute)
        rows.append({"solute": solute, "first_round_mean": by_round.iloc[0],
                     "max_drift_vs_first_round": float((by_round / by_round.iloc[0] - 1).abs().max()),
                     "within_round_cv": float((c.groupby("round")["abs_corrected"].std() / by_round).mean())})
    ax.set_xticks(run.rounds)
    ax.set_xlabel("Round", fontsize=9)
    ax.set_ylabel("DMF control absorbance (blank-corrected)", fontsize=9)
    ax.set_title("DMF control per solute, plate and round (marker = plate)", fontsize=11)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=8, frameon=False, ncol=len(run.solutes))
    fig.tight_layout()
    fig_path = save(fig, outdir / "qc_Q2_controls.png")
    notes = ["Every relative value is divided by its round's control, so control drift between rounds rescales the whole round.",
             "Drift beyond the within-round CV means a different solid load, evaporation or plate attack."]
    return pd.DataFrame(rows), notes, [fig_path]


# ----- detection limit (used by Q5) -----------------------------------------------------------------

def detection_limits(run) -> dict:
    """{solute: MIN_SIGNAL_SIGMAS x reader noise}, the noise being the std of the control spectrum's far-red tail (wavelengths_roundN.csv)."""
    reports = [rep["noise"] for r in run.rounds if (rep := run.wavelength_report(r)) is not None and "noise" in rep.columns]
    return (MIN_SIGNAL_SIGMAS * pd.concat(reports, axis=1).mean(axis=1)).to_dict() if reports else {}


# ----- Q4 spectral QC -------------------------------------------------------------------------------

def q4_spectral(run, outdir, abs_max=ABS_MAX_DEFAULT, nm_range=DEFAULT_NM_RANGE):
    rows, figs = [], []
    for r in run.rounds:
        pm, wl = run.plate_maps[r], run.wavelengths(r)
        blank = run.blank(r)
        shift, scatter = {}, {}
        for p in run.plates(r):
            spec = run.spectra(r, p)
            if spec is None or wl is None:
                continue
            corrected = blank_correct(spec, blank) if blank is not None else spec
            long_wl = corrected.loc[SCATTER_NM[0]:SCATTER_NM[1]]
            if len(corrected.index) >= 50:  # full spectra: peak position is meaningful
                band = corrected.loc[nm_range[0]:nm_range[1], pm.index]
                height = pd.Series([band.loc[wl[s], w] for w, s in pm["solute"].items()], index=pm.index)
                shift[p] = (band.idxmax() - pm["solute"].map(wl)).where(height >= MIN_ABS_FOR_PEAK)
            if len(long_wl):
                scatter[p] = long_wl[pm.index].mean()
        sat = run.wells[(run.wells["round"] == r) & (run.wells["abs_raw"] >= abs_max)]
        rows.append({"round": r, "n_saturated": len(sat), "saturated_wells": " ".join(f"P{p}:{w}" for p, w in zip(sat["plate"], sat["well"]))[:80],
                     "n_peak_shift_gt10nm": int((pd.concat(shift.values()).abs() > 10).sum()) if shift else np.nan,
                     "median_abs_peak_shift_nm": float(pd.concat(shift.values()).abs().median()) if shift else np.nan,
                     "max_scatter_abs": float(pd.concat(scatter.values()).max()) if scatter else np.nan})
        for name, maps, label, cmap, sym in (("peakshift", shift, "Peak minus picked wavelength (nm)", "PuOr", True),
                                             ("scatter", scatter, f"Mean absorbance {SCATTER_NM[0]:.0f}-{SCATTER_NM[1]:.0f} nm", "viridis", False)):
            if not maps:
                continue
            fig, axes = plt.subplots(1, len(maps), figsize=(4.6 * len(maps), 3.6), squeeze=False)
            vmax = max(np.nanmax(np.abs(m.to_numpy(dtype=float))) for m in maps.values())
            vmin = -vmax if sym else 0
            for ax, (p, m) in zip(axes[0], maps.items()):
                im = plate_heatmap(ax, m, f"Plate {p}", cmap=cmap, vmin=vmin, vmax=vmax)
            fig.colorbar(im, ax=axes[0].tolist(), shrink=0.8, pad=0.02).set_label(label, fontsize=9)
            fig.suptitle(f"Round {r}: {label.lower()}", fontsize=11)
            figs.append(save(fig, outdir / f"qc_Q4_{name}_round{r}.png"))
    notes = [f"Saturation: raw absorbance at or above {abs_max}, i.e. a reading the plate reader returned as OVER (PLAN decision 5). "
             "Informational only: by the user's decision an over-range reading is kept as 4.0 and used as a real value "
             "(docs/uv_saturation_estimate.md).",
             f"Peak shift needs full spectra and a band of at least {MIN_ABS_FOR_PEAK} absorbance (grey = too weak); scattering needs readings at 600-700 nm (add a 700 nm read in fixed-wavelength mode).",
             "High scattering = undissolved solid in the light path, which inflates that well."]
    return pd.DataFrame(rows), notes, figs


# ----- Q5 precision against signal ------------------------------------------------------------------

def q5_precision(run, outdir):
    lods = detection_limits(run)
    s = run.samples()
    if not (s["abs_std"] > 0).any():
        table = pd.DataFrame([{"solute": sol, "detection_limit_abs": v,
                               "frac_below_lod": float((s.loc[s["solute"] == sol, "abs_mean"] < v).mean())} for sol, v in lods.items()])
        return table, ["No replicate plates, so there is no within-condition spread to plot; detection limits only."], []
    colors = colors_for(run.solutes)
    fig, ax = plt.subplots(figsize=(5.5, 4))
    rows = []
    for solute in run.solutes:
        g = s[(s["solute"] == solute) & (s["abs_std"] > 0) & (s["abs_mean"] > 0)]
        lod = lods.get(solute, np.nan)
        ax.plot(g["abs_mean"], g["abs_std"], "o", ms=3.5, alpha=0.7, color=colors[solute], label=solute)
        ax.axvline(lod, color=colors[solute], ls="--", lw=0.8)
        slope = np.polyfit(np.log(g["abs_mean"]), np.log(g["abs_std"]), 1)[0] if len(g) > 2 else np.nan
        rows.append({"solute": solute, "detection_limit_abs": lod, "frac_below_lod": float((s[s["solute"] == solute]["abs_mean"] < lod).mean()),
                     "log_slope_std_vs_mean": float(slope)})
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Mean absorbance", fontsize=9)
    ax.set_ylabel("Std across replicate wells", fontsize=9)
    ax.set_title("Precision against signal (dashed = 3 x reader noise)", fontsize=11)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    notes = [f"Detection limit = {MIN_SIGNAL_SIGMAS:g} x the reader noise (std of the control spectrum beyond the absorption bands, wavelengths_roundN.csv).",
             "log slope near 0: constant (reader) noise; near 1: proportional (pipetting/dissolution) noise."]
    return pd.DataFrame(rows), notes, [save(fig, outdir / "qc_Q5_precision.png")]


# ----- Q6 cross-round reproducibility ---------------------------------------------------------------

def q6_retests(run, outdir, cv_table=None):
    s = run.samples()
    re = s[s["kind"] == "retest"]
    if re.empty:
        return pd.DataFrame(), ["No re-tested conditions yet (needs round 2+)."], []
    first = s.drop_duplicates(["solute", "condition_id"]).set_index(["solute", "condition_id"])["rel_mean"]
    re = re.assign(original=[first.get((a, b), np.nan) for a, b in zip(re["solute"], re["condition_id"])])
    colors = colors_for(run.solutes)
    cv_by_solute = (cv_table.groupby("solute")["median_cv"].median().dropna().to_dict()
                    if cv_table is not None and cv_table["median_cv"].notna().any() else {})
    cv = float(np.median(list(cv_by_solute.values()))) if cv_by_solute else None
    fig, ax = plt.subplots(figsize=(5, 4.5))
    rows = []
    for solute in run.solutes:
        g = re[re["solute"] == solute]
        for k, (r, gr) in enumerate(g.groupby("round")):
            ax.plot(gr["original"], gr["rel_mean"], PLATE_MARKERS[k % len(PLATE_MARKERS)], ms=5, color=colors[solute],
                    mfc="none" if k else colors[solute], label=f"{solute} R{r}")
        d = (g["rel_mean"] - g["original"]).abs()
        cv_s = cv_by_solute.get(solute)
        rows.append({"solute": solute, "n_retests": len(g), "mean_abs_diff": float(d.mean()), "plate_cv": cv_s if cv_s is not None else np.nan,
                     "frac_within_2cv": float((d <= 2 * cv_s * g["original"]).mean()) if cv_s else np.nan})
    identity_line(ax)
    if cv:
        x = np.linspace(*ax.get_xlim(), 50)
        ax.fill_between(x, x * (1 - 2 * cv), x * (1 + 2 * cv), color="0.85", label=f"+/- 2 median CV ({cv:.1%})", zorder=0)
    ax.set_xlabel("Relative solubility, first measurement", fontsize=9)
    ax.set_ylabel("Relative solubility, re-test", fontsize=9)
    ax.set_title("Re-tested mixtures across rounds (marker = round)", fontsize=11)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=7, frameon=False, ncol=2)
    fig.tight_layout()
    notes = ["Re-tests repeat a mixture on new solid, a new plate and a refilled reservoir: the only check across rounds.",
             "Grey band: 2 x the median plate-to-plate CV (Q1); frac_within_2cv uses each solute's own CV."]
    return pd.DataFrame(rows), notes, [save(fig, outdir / "qc_Q6_retests.png")]


# ----- driver ---------------------------------------------------------------------------------------

QUESTIONS = {  # what each check is for, printed under its heading in qc_summary.md
    "Q1": "How well do the identical plates of a round agree, and is any plate systematically off? "
          "The spread sets the noise floor: a mixture must beat the best single solvent by more than this to count.",
    "Q2": "Does the DMF control, the denominator of every relative value, stay constant across plates and rounds? "
          "Drift would rescale a whole round and make rounds incomparable.",
    "Q4": "Are any wells saturated, scattering (undissolved solid) or absorbing at the wrong wavelength? "
          "Each would inflate or bias that well's solubility without any extra solute dissolving.",
    "Q5": "Which conditions are measurable at all, and is the noise constant (reader) or proportional to the signal "
          "(pipetting and dissolution)?",
    "Q6": "Does a mixture measured again in a later round, on new solid and a new plate, give the same answer? "
          "This is the only check that rounds can be pooled.",
}


def run_qc(run, outdir, abs_max=ABS_MAX_DEFAULT):
    outdir.mkdir(parents=True, exist_ok=True)
    summary = Summary(f"QC summary: {run.folder.name} (rounds {', '.join(map(str, run.rounds))})")
    q1 = q1_plate_reproducibility(run, outdir)
    checks = [("Q1 plate-to-plate reproducibility", q1), ("Q2 control stability", q2_control_stability(run, outdir)),
              ("Q4 spectral QC", q4_spectral(run, outdir, abs_max)), ("Q5 precision against signal", q5_precision(run, outdir)),
              ("Q6 cross-round re-tests", q6_retests(run, outdir, q1[0]))]
    for title, (table, notes, figs) in checks:
        summary.section(title, notes, table, figs, QUESTIONS[title.split()[0]])
    return summary.write(outdir / "qc_summary.md")
