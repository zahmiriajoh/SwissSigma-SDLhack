"""The QC plate: one extra plate per round with solvent-only blanks and a calibration series (PLAN.md Q-a).

Layout (96 wells, row order):
    calibration   every solvent x every solute x LOADINGS       (7 x 4 x 2 = 56 wells by default)
    blank         every pure solvent, every allowed equal binary of the green solvents, then allowed equal ternaries
                  (forbidden pairs from production/config.toml are skipped, so some wells may stay empty)

Calibration wells get a known fraction of the nominal solid mass (`loading`: 1.0 = the mass used in the sample
plates) and 300 uL of one pure solvent, so absorbance against loading gives the response per unit mass and shows
where a solute stops dissolving. Blank wells carry no solid. The robot CSV follows bo_bridge's format (well, solute,
condition_id, vol_<solvent>_ul) and is run as a separate 1-plate run of sdl_solubility_ot2.py.
"""
from itertools import combinations

import pandas as pd

from production.config import REFERENCE_SOLVENT, is_allowed

from .spectra import WELLS

LOADINGS = (0.5, 1.0)  # fractions of the nominal solid mass in the calibration series


def _mix_rows(solvents, n):
    """Equal-part mixtures of n solvents, skipping forbidden (immiscible) pairs."""
    return [{s: 1 / n for s in combo} for combo in combinations(solvents, n) if is_allowed(combo)]


def qc_plate_map(plate_map, loadings=LOADINGS) -> pd.DataFrame:
    """QC plate map for the round of `plate_map` (a bo_bridge plate map indexed by well)."""
    round_ = int(plate_map["round"].iloc[0])
    frac_cols = [c for c in plate_map.columns if c.startswith("frac_")]
    solvents = [c[len("frac_"):] for c in frac_cols]
    green = [s for s in solvents if s != REFERENCE_SOLVENT]
    solutes = list(dict.fromkeys(plate_map["solute"]))
    total_ul = int(round(plate_map[[c.replace("frac_", "vol_") + "_ul" for c in frac_cols]].sum(axis=1).iloc[0])) \
        if f"vol_{solvents[0]}_ul" in plate_map.columns else 300

    rows = []
    for solute in solutes:
        for solvent in solvents:
            for loading in loadings:
                rows.append(dict(role="calibration", solvent=solvent, solute=solute, loading=loading,
                                 condition_id=f"R{round_}_cal_{solvent}_{solute}_L{loading:g}", mix={solvent: 1.0}))
    blanks = [{s: 1.0} for s in solvents] + _mix_rows(green, 2) + _mix_rows(green, 3)
    for mix in blanks[: len(WELLS) - len(rows)]:
        label = "+".join(mix)
        rows.append(dict(role="blank", solvent=label if len(mix) == 1 else "", solute="", loading=float("nan"),
                         condition_id=f"R{round_}_blank_{label}", mix=mix))
    if len(rows) > len(WELLS):
        raise ValueError(f"QC layout needs {len(rows)} wells; reduce the number of loadings")

    out = pd.DataFrame({"round": round_, "well": WELLS[: len(rows)],
                        **{k: [r[k] for r in rows] for k in ("role", "solvent", "solute", "loading", "condition_id")}})
    for s in solvents:
        out[f"frac_{s}"] = [round(r["mix"].get(s, 0.0), 4) for r in rows]
    for s in solvents:
        out[f"vol_{s}_ul"] = (out[f"frac_{s}"] * total_ul).round().astype(int)
    return out.set_index("well")


def robot_csv(qc_map) -> pd.DataFrame:
    """bo_bridge-format robot CSV: well, solute ('blank' for solvent-only wells), condition_id, vol_<solvent>_ul."""
    vol_cols = [c for c in qc_map.columns if c.startswith("vol_")]
    used = [c for c in vol_cols if qc_map[c].sum() > 0]
    out = qc_map.reset_index()[["well", "solute", "condition_id"] + used]
    out["solute"] = out["solute"].replace("", "blank")
    return out


def write_qc_layout(plate_map, outdir, loadings=LOADINGS):
    """Write qc_plate_map_roundN.csv and ot_input_roundN_qc.csv; returns the QC map."""
    qc = qc_plate_map(plate_map, loadings)
    r = int(qc["round"].iloc[0])
    qc.to_csv(outdir / f"qc_plate_map_round{r}.csv")
    robot_csv(qc).to_csv(outdir / f"ot_input_round{r}_qc.csv", index=False)
    return qc
