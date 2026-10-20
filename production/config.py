"""Read production/config.toml and expose it as plain constants (standard library only, so bo_bridge.py can use it too).

    from production.config import SOLUTES, ALL_SOLVENTS, GREEN_SOLVENTS, SOLVENT_TROUGHS, TOTAL_UL, FIRST_ROUND, ...

or, from a script that is not a package member:

    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("production_config", pathlib.Path(REPO, "production", "config.py"))
    cfg = importlib.util.module_from_spec(spec); spec.loader.exec_module(cfg)
"""
import re
import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.toml")


def load(path=CONFIG_PATH) -> dict:
    """The validated config as a dict; raises ValueError on an inconsistent file."""
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    solvents = [s["name"] for s in cfg["solvents"]]
    solutes = [s["name"] for s in cfg["solutes"]]
    bad = [n for n in solvents + solutes if not re.fullmatch(r"[A-Za-z0-9_\-]+", n) or " " in n]
    if bad:
        raise ValueError(f"names must be plain identifiers (no spaces): {bad}")
    if any("-" in n for n in solvents):
        raise ValueError("solvent names appear in CSV columns and ids: use labels for hyphens (e.g. name iPrOH, label i-PrOH)")
    if len(set(solvents)) != len(solvents) or len(set(solutes)) != len(solutes):
        raise ValueError("duplicate solvent or solute name")
    troughs = [s["trough"] for s in cfg["solvents"]]
    if len(set(troughs)) != len(troughs):
        raise ValueError(f"two solvents share a trough: {troughs}")
    if cfg["reference"]["solvent"] not in solvents:
        raise ValueError("reference solvent is not in the solvent list")
    if cfg["well"]["total_ul"] % cfg["well"]["min_ul"]:
        raise ValueError("total_ul must be a multiple of min_ul")
    return cfg


_cfg = load()

FIRST_ROUND = _cfg["numbering"]["first_round"]
FIRST_PLATE = _cfg["numbering"]["first_plate"]
FIRST_CONDITION = _cfg["numbering"]["first_condition"]

TOTAL_UL = _cfg["well"]["total_ul"]
MIN_UL = _cfg["well"]["min_ul"]
MAX_SOLVENTS_PER_MIXTURE = MAX_SOLVENTS_PER_MIX = _cfg["well"]["max_solvents_per_mixture"]  # SDL_BO and bo_bridge spellings

N_PLATES = _cfg["plates"]["per_round"]
TROUGH_FILL_UL = _cfg["plates"]["trough_fill_ul"]
TROUGH_DEAD_UL = _cfg["plates"]["trough_dead_ul"]
TROUGH_USABLE_UL = TROUGH_FILL_UL - TROUGH_DEAD_UL

REFERENCE_SOLVENT = _cfg["reference"]["solvent"]
ALL_SOLVENTS = [s["name"] for s in _cfg["solvents"]]                     # reference first, as in bo_bridge
GREEN_SOLVENTS = [s for s in ALL_SOLVENTS if s != REFERENCE_SOLVENT]
SOLVENT_LABELS = {s["name"]: s["label"] for s in _cfg["solvents"]}
SOLVENT_TROUGHS = {s["name"]: [s["trough"]] for s in _cfg["solvents"]}   # bo_bridge / protocol format (list per solvent)
PLATE_ATTACKERS = [s["name"] for s in _cfg["solvents"] if s["attacks_polystyrene"]]

SOLUTES = [s["name"] for s in _cfg["solutes"]]
SOLUTE_WAVELENGTH_NM = {s["name"]: s.get("wavelength_nm") for s in _cfg["solutes"]}  # None = unknown, pick from data
