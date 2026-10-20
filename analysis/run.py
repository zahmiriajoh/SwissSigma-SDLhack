"""One campaign folder (all rounds) as produced by bo_bridge.py layout / merge and `analysis reduce`.

Expected files in the folder, per round N (missing optional ones are skipped by the analyses that need them):
    plate_map_roundN.csv            bo_bridge layout      well -> solute, condition_id, role, frac_<solvent>
    results_roundN_wells.csv        bo_bridge merge       per well and plate: abs_raw, abs_blank, abs_corrected, rel_to_DMF
    bo_dataset.csv, bo_dataset_shared.csv   bo_bridge merge   per solute x condition / per shared condition, all rounds
    wavelengths_roundN.csv          analysis reduce       solute -> wavelength_nm                      (optional)
    reader_roundN_plate{P}.csv, reader_roundN_blank.csv   plate reader   spectra                      (optional)
    reader_roundN_qc.csv, qc_plate_map_roundN.csv        QC plate: blanks + calibration series       (optional)
    plate_log_roundN.csv            lab notes             plate, read_delay_min (shake end -> read)   (optional)
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .spectra import SpectraError, read_plate_map, read_spectra, synthetic_blank

KINDS = ["control", "seed", "exploit", "explore", "retest"]
NOISE_FLOOR = 0.01  # per-well relative noise assumed when a campaign has neither replicate plates nor re-tests
_KIND_TAGS = {"dmfref": "control", "grid": "seed", "seed": "seed", "exploit": "exploit", "explore": "explore"}


def condition_kind(condition_id, round_) -> str:
    """'R2_exploit03' in round 2 -> 'exploit'; an id first used in an earlier round -> 'retest'."""
    m = re.fullmatch(r"R(\d+)_([A-Za-z]+?)(?:ref)?\d*", str(condition_id))
    if m is None:
        return "seed"
    if m.group(2).lower() == "dmf":
        return "control"
    if int(m.group(1)) != int(round_):
        return "retest"
    return _KIND_TAGS.get(m.group(2).lower(), "seed")


def frac_columns(df) -> list:
    return [c for c in df.columns if c.startswith("frac_")]


def solvent_names(df) -> list:
    return [c[len("frac_"):] for c in frac_columns(df)]


def mixture_key(row, cols) -> str:
    """Composition string like '0.5 EtOAc + 0.5 DMC' (fractions rounded to 3 dp), used to pool a mixture across rounds."""
    parts = [(float(row[c]), c[len("frac_"):]) for c in cols if float(row[c]) > 0]
    return " + ".join(f"{f:.3g} {s}" for f, s in parts)


class Run:
    """Lazy reader for a campaign folder."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.rounds = sorted(int(m.group(1)) for p in self.folder.glob("plate_map_round*.csv")
                             if (m := re.search(r"round(\d+)\.csv$", p.name)))
        if not self.rounds:
            raise SpectraError(f"{self.folder}: no plate_map_round*.csv found")
        self.plate_maps = {r: read_plate_map(self.folder / f"plate_map_round{r}.csv") for r in self.rounds}
        self.wells = self._read_wells()
        self.dataset = self._with_kind(pd.read_csv(self.folder / "bo_dataset.csv"))
        shared = self.folder / "bo_dataset_shared.csv"
        self.shared = self._with_kind(pd.read_csv(shared)) if shared.exists() else None
        self.solutes = list(dict.fromkeys(self.dataset["solute"]))
        self.solvents = solvent_names(self.dataset)
        self.green_solvents = [s for s in self.solvents if s != "DMF"]

    # ----- per-round optional files -----------------------------------------------------------
    def _optional(self, name):
        path = self.folder / name
        return path if path.exists() else None

    def wavelengths(self, r):
        path = self._optional(f"wavelengths_round{r}.csv")
        return pd.read_csv(path, index_col=0)["wavelength_nm"] if path else None

    def plates(self, r) -> list:
        """Plate numbers with a results row in round r."""
        return sorted(self.wells.loc[self.wells["round"] == r, "plate"].unique())

    def spectra(self, r, plate):
        path = self._optional(f"reader_round{r}_plate{plate}.csv")
        return read_spectra(path) if path else None

    def blank_spectra(self, r):
        path = self._optional(f"reader_round{r}_blank.csv")
        return read_spectra(path) if path else None

    def blank(self, r):
        """Blank spectra for round r: the solvent-only plate if read, else built from the QC plate's pure-solvent blanks."""
        plate = self.blank_spectra(r)
        if plate is not None:
            return plate
        qc_map, qc_spec = self.qc_map(r), self.qc_spectra(r)
        return synthetic_blank(qc_spec, qc_map, self.plate_maps[r]) if qc_map is not None and qc_spec is not None else None

    def qc_map(self, r):
        path = self._optional(f"qc_plate_map_round{r}.csv")
        return pd.read_csv(path, index_col="well") if path else None

    def qc_spectra(self, r):
        path = self._optional(f"reader_round{r}_qc.csv")
        return read_spectra(path) if path else None

    def plate_log(self):
        """round, plate, read_delay_min for every logged plate, or None."""
        frames = [pd.read_csv(p).assign(round=r) for r in self.rounds if (p := self._optional(f"plate_log_round{r}.csv"))]
        return pd.concat(frames, ignore_index=True) if frames else None

    # ----- tables ------------------------------------------------------------------------------
    def _read_wells(self) -> pd.DataFrame:
        frames = []
        for r in self.rounds:
            path = self.folder / f"results_round{r}_wells.csv"
            if not path.exists():
                raise SpectraError(f"{path} missing: run bo_bridge.py merge for round {r} first")
            frames.append(pd.read_csv(path))
        wells = pd.concat(frames, ignore_index=True)
        wells["kind"] = [condition_kind(c, r) for c, r in zip(wells["condition_id"], wells["round"])]
        return wells

    @staticmethod
    def _with_kind(df) -> pd.DataFrame:
        df["kind"] = [condition_kind(c, r) for c, r in zip(df["condition_id"], df["round"])]
        cols = frac_columns(df)
        df["mixture"] = [mixture_key(row, cols) for _, row in df.iterrows()]
        return df

    def samples(self) -> pd.DataFrame:
        """Dataset rows that are not DMF controls."""
        return self.dataset[self.dataset["is_reference"] == 0]

    def well_noise(self) -> dict:
        """Per solute: the per-well noise of a relative value, pooled over all conditions (root mean square of rel_std).
        Falls back to the spread of re-tested mixtures across rounds, then to NOISE_FLOOR, when no plate replicates exist."""
        s = self.samples()
        out = {}
        for solute, g in s.groupby("solute"):
            reps = g.loc[g["n_obs"] > 1, "rel_std"].dropna()
            if len(reps):
                out[solute] = float(np.sqrt((reps ** 2).mean()))
                continue
            retest = g.groupby("mixture")["rel_mean"].std().dropna()
            out[solute] = float(np.sqrt((retest ** 2).mean())) if len(retest) else NOISE_FLOOR
        return out

    def control_drift(self) -> dict:
        """Per solute: relative std of the DMF-control mean across rounds (0 with one round). Every value of a round is
        divided by its control, so this is how far a round's normalisation can be off relative to the other rounds."""
        ctrl = self.wells[self.wells["role"] == "control"].groupby(["solute", "round"])["abs_corrected"].mean()
        return {sol: float(g.std() / g.mean()) if len(g) > 1 else 0.0 for sol, g in ctrl.groupby(level=0)}

    def pooled(self) -> pd.DataFrame:
        """One row per solute x mixture, pooled over rounds.

        rel = mean of the per-round rel_mean. rel_err is a standard error: the larger of the within-round SE
        (pooled per-well noise / sqrt(n_obs)) and the between-round spread, combined in quadrature with the normalisation
        error rel x max(control drift between rounds, control SE within a round).
        """
        s = self.samples().copy()
        noise, drift = self.well_noise(), self.control_drift()
        ref = self.dataset[self.dataset["is_reference"] == 1].set_index(["round", "solute"])["n_obs"]
        s["se_within"] = [noise[sol] / np.sqrt(n) for sol, n in zip(s["solute"], s["n_obs"])]
        s["se_norm"] = [rel * max(drift[sol], noise[sol] / np.sqrt(ref.get((r, sol), 1)))
                        for rel, sol, r in zip(s["rel_mean"], s["solute"], s["round"])]
        g = s.groupby(["solute", "mixture"], sort=False)
        out = g.agg(rel=("rel_mean", "mean"), within=("se_within", "mean"), between=("rel_mean", "std"), norm=("se_norm", "mean"),
                    n=("n_obs", "sum"), n_solvents=("n_solvents", "first"), rounds=("round", lambda x: sorted(set(x))))
        fr = g[frac_columns(s)].first()
        out["rel_err"] = np.sqrt(out[["within", "between"]].fillna(0).max(axis=1) ** 2 + out["norm"] ** 2)
        return pd.concat([out.drop(columns=["within", "between", "norm"]), fr], axis=1).reset_index()

    def pooled_objective(self) -> pd.DataFrame:
        """One row per mixture measured on every solute: rel_<solute>, obj_min_rel, its error, n_solvents, fractions."""
        p = self.pooled()
        wide = p.pivot(index="mixture", columns="solute", values="rel").dropna()
        err = p.pivot(index="mixture", columns="solute", values="rel_err").loc[wide.index]
        worst = wide.idxmin(axis=1)
        out = wide.add_prefix("rel_")
        out["obj_min_rel"] = wide.min(axis=1)
        out["obj_err"] = [err.loc[m, s] for m, s in worst.items()]
        meta = p.drop_duplicates("mixture").set_index("mixture")
        out["n_solvents"] = meta.loc[out.index, "n_solvents"]
        out["first_round"] = [min(r) for r in meta.loc[out.index, "rounds"]]
        return pd.concat([out, meta.loc[out.index, frac_columns(p)]], axis=1).reset_index()
