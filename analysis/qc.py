"""Experiment quality (PLAN.md Q1-Q7): reproducibility, control drift, blank/plate attack, spectra, precision,
re-tests and calibration. Each check returns (summary table, notes, figure paths); run_qc writes qc_summary.md.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .plots import (OKABE_ITO, PLATE_MARKERS, colors_for, identity_line, panel_grid, plate_heatmap, save)
from .spectra import DEFAULT_NM_RANGE, blank_correct
from .summary import Summary

ESTERS_ETHERS = ["EtOAc", "iPrOAc", "2MeTHF", "CPME"]  # solvents that attack polystyrene most
PLATE_OFFSET_FLAG = 0.05       # a plate whose median deviates from the others by more than this is flagged
SCATTER_NM = (600.0, 800.0)    # no solute absorbs here: signal = scattering by undissolved solid
MIN_ABS_FOR_PEAK = 0.05     # peak position is only meaningful for wells whose corrected band is at least this high
LINEAR_RESIDUAL = 0.05         # calibration: a level is "linear" while its residual is within 5 % of the fit
ABS_MAX_DEFAULT = 2.5          # reader linear range (PLAN Q-b unknown; placeholder)


def _lin_fit(x, y):
    """Least-squares y = a x (through the origin): returns (slope, R^2)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    a = (x @ y) / (x @ x) if (x @ x) > 0 else np.nan
    ss_res, ss_tot = ((y - a * x) ** 2).sum(), ((y - y.mean()) ** 2).sum()
    return a, 1 - ss_res / ss_tot if ss_tot > 0 else np.nan


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
        rows.append({"solute": solute, "round1_mean": by_round.iloc[0],
                     "max_drift_vs_round1": float((by_round / by_round.iloc[0] - 1).abs().max()),
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


# ----- Q3 blank plate and polystyrene attack --------------------------------------------------------

def blank_model(run):
    """abs_blank ~ sum_s frac_s * b_s per solute (least squares): coefficients, residual std and R^2."""
    cols = [f"frac_{s}" for s in run.solvents]
    pm = pd.concat([m.assign(round=r) for r, m in run.plate_maps.items()])
    w = run.wells.drop_duplicates(["round", "well", "solute"]).merge(
        pm.reset_index()[["round", "well"] + cols], on=["round", "well"])
    out = {}
    for solute, g in w.groupby("solute"):
        X, y = g[cols].to_numpy(float), g["abs_blank"].to_numpy(float)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ coef
        r2 = 1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum() if y.std() > 0 else np.nan
        out[solute] = {"coef": pd.Series(coef, index=run.solvents), "resid_std": float(resid.std()), "r2": float(r2)}
    return w, out


def qc_blank_additivity(run) -> pd.DataFrame:
    """QC-plate mixture blanks: measured absorbance (at each solute's wavelength) against the pure-solvent prediction."""
    rows = []
    for r in run.rounds:
        qc_map, spec, wl = run.qc_map(r), run.qc_spectra(r), run.wavelengths(r)
        if qc_map is None or spec is None or wl is None:
            continue
        blanks = qc_map[qc_map["role"] == "blank"]
        cols = [c for c in blanks.columns if c.startswith("frac_")]
        is_pure = blanks["solvent"].notna() & (blanks["solvent"].astype(str) != "")
        pure = {row["solvent"]: spec[w] for w, row in blanks[is_pure].iterrows()}
        for w, row in blanks[~is_pure].iterrows():
            predicted = sum(row[c] * pure[c[len("frac_"):]] for c in cols if row[c] > 0)
            for solute, nm in wl.items():
                rows.append({"round": r, "well": w, "solute": solute, "n_solvents": int((row[cols] > 0).sum()),
                             "measured": float(spec.loc[nm, w]), "predicted": float(predicted.loc[nm])})
    return pd.DataFrame(rows)


def q3_blank_and_attack(run, outdir):
    w, model = blank_model(run)
    additivity = qc_blank_additivity(run)
    colors = colors_for(run.solutes)
    cols = [f"frac_{s}" for s in run.solvents]
    w["dominant"] = w[cols].idxmax(axis=1).str[len("frac_"):]
    w["ester_ether"] = w[[f"frac_{s}" for s in ESTERS_ETHERS if s in run.solvents]].sum(axis=1)
    log = run.plate_log()
    panels = 2 + (log is not None) + (not additivity.empty)
    fig, axes = panel_grid(panels, panels, (4.6, 3.6))
    ax = axes[0]
    x_of = {s: i for i, s in enumerate(run.solvents)}
    for j, solute in enumerate(run.solutes):
        g = w[w["solute"] == solute]
        jitter = (j - (len(run.solutes) - 1) / 2) * 0.15
        ax.plot(g["dominant"].map(x_of) + jitter, g["abs_blank"], "o", ms=3, color=colors[solute], alpha=0.6, label=solute)
    ax.set_xticks(range(len(run.solvents)), run.solvents, fontsize=8, rotation=30)
    ax.set_ylabel("Blank absorbance at solute wavelength", fontsize=9)
    ax.set_title("By dominant solvent", fontsize=10)
    ax.legend(fontsize=7, frameon=False)
    ax = axes[1]
    for solute in run.solutes:
        g = w[w["solute"] == solute]
        ax.plot(g["ester_ether"], g["abs_blank"], "o", ms=3, color=colors[solute], alpha=0.6)
    ax.set_xlabel("Ester + ether fraction", fontsize=9)
    ax.set_ylabel("Blank absorbance", fontsize=9)
    ax.set_title("Polystyrene-attacking solvents", fontsize=10)
    if log is not None:
        ax = axes[2]
        plate_mean = run.wells.groupby(["round", "plate", "solute"])["abs_corrected"].median().reset_index()
        plate_mean["rel"] = plate_mean["abs_corrected"] / plate_mean.groupby(["round", "solute"])["abs_corrected"].transform("mean") - 1
        d = plate_mean.assign(plate=plate_mean["plate"].astype(str)).merge(log.assign(plate=log["plate"].astype(str)), on=["round", "plate"])
        for solute in run.solutes:
            g = d[d["solute"] == solute]
            ax.plot(g["read_delay_min"], g["rel"] * 100, "o", ms=4, color=colors[solute])
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xlabel("Shake end to read (min)", fontsize=9)
        ax.set_ylabel("Plate median vs round mean (%)", fontsize=9)
        ax.set_title("Read delay effect on sample plates", fontsize=10)
    if not additivity.empty:
        ax = axes[-1]
        for solute in run.solutes:
            g = additivity[additivity["solute"] == solute]
            ax.plot(g["predicted"], g["measured"], "o", ms=3, color=colors[solute], alpha=0.7)
        identity_line(ax)
        ax.set_xlabel("Predicted from pure-solvent blanks", fontsize=9)
        ax.set_ylabel("Measured mixture blank", fontsize=9)
        ax.set_title("QC plate: is the blank additive?", fontsize=10)
    for ax in axes:
        ax.tick_params(labelsize=8)
    fig.suptitle("Blank wells: solvent background and plate attack", fontsize=11)
    fig.tight_layout()
    fig_path = save(fig, outdir / "qc_Q3_blank.png")
    table = pd.DataFrame([{"solute": s, **{f"b_{k}": v for k, v in m["coef"].items()},
                           "resid_std": m["resid_std"], "r2": m["r2"]} for s, m in model.items()])
    notes = ["b_<solvent>: blank absorbance of the pure solvent at that solute's wavelength (additive fit over all blank wells).",
             *([f"QC-plate mixture blanks: measured minus additive prediction = {additivity['measured'].sub(additivity['predicted']).abs().mean():.4f} "
                f"absorbance on average (n = {len(additivity)})."] if not additivity.empty else []),
             "Low R^2 or large residuals mean the blank is not additive in composition, i.e. plate attack or solvent interaction.",
             "Read-delay panel appears only when plate_log_roundN.csv files exist."]
    return table, notes, [fig_path]


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
        sat = run.wells[(run.wells["round"] == r) & (run.wells["abs_raw"] > abs_max)]
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
    notes = [f"Saturation: raw absorbance above {abs_max} (reader linear range placeholder, PLAN Q-b).",
             f"Peak shift needs full spectra and a band of at least {MIN_ABS_FOR_PEAK} absorbance (grey = too weak); scattering needs readings at 600-800 nm (add a 700 nm read in fixed-wavelength mode).",
             "High scattering = undissolved solid in the light path, which inflates that well."]
    return pd.DataFrame(rows), notes, figs


# ----- Q5 precision against signal ------------------------------------------------------------------

def q5_precision(run, outdir):
    _, model = blank_model(run)
    s = run.samples()
    if not (s["abs_std"] > 0).any():
        lod = {sol: 3 * m["resid_std"] for sol, m in model.items()}
        table = pd.DataFrame([{"solute": sol, "detection_limit_abs": v,
                               "frac_below_lod": float((s.loc[s["solute"] == sol, "abs_mean"] < v).mean())} for sol, v in lod.items()])
        return table, ["No replicate plates, so there is no within-condition spread to plot; detection limits only."], []
    colors = colors_for(run.solutes)
    fig, ax = plt.subplots(figsize=(5.5, 4))
    rows = []
    for solute in run.solutes:
        g = s[(s["solute"] == solute) & (s["abs_std"] > 0) & (s["abs_mean"] > 0)]
        lod = 3 * model[solute]["resid_std"]
        ax.plot(g["abs_mean"], g["abs_std"], "o", ms=3.5, alpha=0.7, color=colors[solute], label=solute)
        ax.axvline(lod, color=colors[solute], ls="--", lw=0.8)
        slope = np.polyfit(np.log(g["abs_mean"]), np.log(g["abs_std"]), 1)[0] if len(g) > 2 else np.nan
        rows.append({"solute": solute, "detection_limit_abs": lod, "frac_below_lod": float((s[s["solute"] == solute]["abs_mean"] < lod).mean()),
                     "log_slope_std_vs_mean": float(slope)})
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Mean absorbance (blank-corrected)", fontsize=9)
    ax.set_ylabel("Std across replicate wells", fontsize=9)
    ax.set_title("Precision against signal (dashed = 3 x blank noise)", fontsize=11)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    notes = ["Detection limit = 3 x residual std of the blank model (Q3).",
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


# ----- Q7 calibration (QC plate) ------------------------------------------------------------------

def calibration_table(qc_map, qc_spectra, wavelengths):
    """Per (solvent, solute): absorbance at the solute's wavelength minus that solvent's pure blank, slope through the origin,
    R^2 and the linear range (largest loading whose residual is within LINEAR_RESIDUAL of the fit). Also the per-well table."""
    blanks = qc_map[(qc_map["role"] == "blank") & qc_map["solvent"].notna() & (qc_map["solvent"].astype(str) != "")]
    blank_at = {(row["solvent"], solute): float(qc_spectra.loc[nm, w]) for w, row in blanks.iterrows() for solute, nm in wavelengths.items()}
    cal = qc_map[qc_map["role"] == "calibration"].copy()
    cal["absorbance"] = [float(qc_spectra.loc[wavelengths[row["solute"]], w]) for w, row in cal.iterrows()]
    cal["corrected"] = [a - blank_at.get((row["solvent"], row["solute"]), 0.0) for a, (_, row) in zip(cal["absorbance"], cal.iterrows())]
    rows = []
    for (solvent, solute), g in cal.groupby(["solvent", "solute"]):
        g = g.sort_values("loading")
        lo, hi = g.iloc[0], g.iloc[-1]
        slope = lo["corrected"] / lo["loading"]  # response per unit mass at the lowest loading, the one most likely fully dissolved
        resid = (g["corrected"] - slope * g["loading"]).abs() / max(abs(slope * lo["loading"]), 1e-9)
        linear = g["loading"][resid <= LINEAR_RESIDUAL]
        ratio = (hi["corrected"] / lo["corrected"]) / (hi["loading"] / lo["loading"]) if lo["corrected"] > 0 and len(g) > 1 else np.nan
        rows.append({"solvent": solvent, "solute": solute, "slope_per_loading": slope, "top_to_bottom_linearity": ratio,
                     "linear_up_to": float(linear.max()) if len(linear) else 0.0, "n_levels": len(g)})
    return pd.DataFrame(rows), cal


def q7_calibration(run, outdir):
    rows, figs = [], []
    for r in run.rounds:
        qc_map, qc_spec, wl = run.qc_map(r), run.qc_spectra(r), run.wavelengths(r)
        if qc_map is None or qc_spec is None or wl is None:
            continue
        table, cal = calibration_table(qc_map, qc_spec, wl)
        table["round"] = r
        ctrl = run.wells[(run.wells["round"] == r) & (run.wells["role"] == "control")].groupby("solute")["abs_corrected"].mean()
        dmf = table[table["solvent"] == "DMF"].set_index("solute")["slope_per_loading"]
        table["dmf_control_recovery"] = table["solute"].map(lambda s: ctrl.get(s, np.nan) / dmf.get(s, np.nan))
        rows.append(table)
        colors = colors_for(run.solvents)
        fig, axes = panel_grid(len(run.solutes), 2, (5, 3.4))
        for ax, solute in zip(axes, run.solutes):
            for k, solvent in enumerate(run.solvents):
                g = cal[(cal["solute"] == solute) & (cal["solvent"] == solvent)].sort_values("loading")
                if g.empty:
                    continue
                ax.plot([0, *g["loading"]], [0, *g["corrected"]], PLATE_MARKERS[k % len(PLATE_MARKERS)] + "-", ms=4, lw=0.8,
                        color=colors[solvent], label=solvent, mfc="none" if k >= len(PLATE_MARKERS) else colors[solvent])
            ax.set_title(f"{solute} at {wl.get(solute, np.nan):.0f} nm", fontsize=10)
            ax.set_xlabel("Loading (fraction of nominal mass)", fontsize=9)
            ax.set_ylabel("Absorbance minus solvent blank", fontsize=9)
            ax.tick_params(labelsize=8)
        axes[0].legend(fontsize=7, frameon=False, ncol=2)
        fig.suptitle(f"Round {r}: calibration series per solvent (QC plate)", fontsize=11)
        fig.tight_layout()
        figs.append(save(fig, outdir / f"qc_Q7_calibration_round{r}.png"))
    if not rows:
        return pd.DataFrame(), ["No QC plate (qc_plate_map_roundN.csv + reader_roundN_qc.csv) found."], []
    notes = ["slope_per_loading: blank-corrected absorbance per unit of nominal solid mass, from the lowest loading (most likely fully dissolved).",
             "top_to_bottom_linearity: 1.0 = the highest loading reads in proportion to the lowest; well below 1 = solubility-limited (the series bends over). linear_up_to: largest loading within 5 % of that line.",
             "dmf_control_recovery: sample-plate DMF control / DMF calibration slope; 1.0 means the control is fully dissolved."]
    return pd.concat(rows, ignore_index=True), notes, figs


# ----- driver ---------------------------------------------------------------------------------------

def run_qc(run, outdir, abs_max=ABS_MAX_DEFAULT):
    outdir.mkdir(parents=True, exist_ok=True)
    summary = Summary(f"QC summary: {run.folder.name} (rounds {', '.join(map(str, run.rounds))})")
    q1 = q1_plate_reproducibility(run, outdir)
    checks = [("Q1 plate-to-plate reproducibility", q1), ("Q2 control stability", q2_control_stability(run, outdir)),
              ("Q3 blank wells and plate attack", q3_blank_and_attack(run, outdir)),
              ("Q4 spectral QC", q4_spectral(run, outdir, abs_max)), ("Q5 precision against signal", q5_precision(run, outdir)),
              ("Q6 cross-round re-tests", q6_retests(run, outdir, q1[0])), ("Q7 calibration", q7_calibration(run, outdir))]
    for title, (table, notes, figs) in checks:
        summary.section(title, notes, table, figs)
    return summary.write(outdir / "qc_summary.md")
