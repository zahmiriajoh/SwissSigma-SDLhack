"""The seams: production/config.toml <-> bo_bridge.py <-> OT-2 protocol <-> SDL_BO <-> fake plate reader. bo_bridge is run as
the real script."""
import ast
import subprocess
import sys

import pandas as pd
import pytest

from SDL_BO import campaign, dataset, space
from conftest import DEBUG_DIR, OT_EXAMPLES, PROTOCOLS, REPO, load_bo_bridge, run_bridge
from production import config

R0, P = config.FIRST_ROUND, config.FIRST_PLATE


def protocol_constant(path, name):
    """Literal value of a module-level constant in a protocol file, without importing opentrons."""
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and node.targets[0].id == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path}")


def test_bo_bridge_and_sdl_bo_follow_the_config():
    bridge = load_bo_bridge()
    assert space.ALL_SOLVENTS == bridge.ALL_SOLVENTS == config.ALL_SOLVENTS
    assert space.REFERENCE_SOLVENT == bridge.REFERENCE_SOLVENT == config.REFERENCE_SOLVENT
    assert space.TOTAL_UL == bridge.TOTAL_UL and space.MIN_UL == bridge.MIN_UL
    assert space.MAX_SOLVENTS_PER_MIXTURE == bridge.MAX_SOLVENTS_PER_MIX
    assert space.TROUGH_USABLE_UL == bridge.TROUGH_USABLE_UL and space.N_PLATES == bridge.N_PLATES
    assert space.N_SOLUTES == len(bridge.SOLUTES) == len(config.SOLUTES)
    assert campaign.N_CONDITIONS == (len(bridge.PLATE_WELLS) // len(bridge.SOLUTES) - bridge.CONTROLS_PER_SOLUTE)
    assert space.FRACTION_COLUMNS == bridge.FRAC_COLS


def test_production_protocol_is_the_simulated_one():
    """tools/check_all.py simulates the OT protocols/ copy; the lab uploads the production/ copy."""
    assert len({p.read_text() for p in PROTOCOLS}) == 1


@pytest.mark.parametrize("protocol", PROTOCOLS, ids=lambda p: p.parent.name)
def test_protocols_mirror_the_config_troughs(protocol):
    troughs = protocol_constant(protocol, "SOLVENT_TROUGHS")
    assert {k: v for k, v in troughs.items() if k != "diluent"} == config.SOLVENT_TROUGHS
    used = {well for wells in config.SOLVENT_TROUGHS.values() for well in wells}
    assert not used & set(troughs.get("diluent", []))  # a spare trough on H1 means dropping the protocol's diluent entry
    assert protocol_constant(protocol, "TROUGH_FILL_UL") == config.TROUGH_FILL_UL
    assert protocol_constant(protocol, "TROUGH_DEAD_UL") == config.TROUGH_DEAD_UL


@pytest.mark.parametrize("protocol", PROTOCOLS, ids=lambda p: p.parent.name)
def test_blank_plate_wells_match_what_the_analysis_reads(protocol):
    """The protocol puts solvent n in row <its trough's row> of column round - FIRST_ROUND + 1; reduce must read the same wells."""
    from analysis.spectra import solvent_wells
    troughs, first = protocol_constant(protocol, "SOLVENT_TROUGHS"), protocol_constant(protocol, "FIRST_ROUND")
    assert first == config.FIRST_ROUND
    for r in (first, first + 2):
        filled = {n: f"{wells[0][0]}{r - first + 1}" for n, wells in troughs.items() if n != "diluent"}
        assert filled == solvent_wells(r)


def test_fake_plate_reader_names_follow_the_config():
    import fake_plate_reader as fpr
    assert fpr.ALL_SOLVENTS == config.ALL_SOLVENTS and list(fpr.PEAK_NM) == config.SOLUTES


def test_bo_bridge_layout_accepts_seed_design(tmp_path):
    suggestions = tmp_path / f"suggestions_round{R0}.csv"
    campaign.seed_design().to_csv(suggestions, index=False)
    result = run_bridge("layout", "--round", R0, "--suggestions", suggestions, "--outdir", tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "snapped" not in result.stdout  # 5 uL grid: nothing gets rounded
    plate_map = pd.read_csv(tmp_path / f"plate_map_round{R0}.csv")
    assert plate_map["condition_id"].iloc[1] == f"R{R0}_seed{config.FIRST_CONDITION:02d}" and plate_map["replicate"].min() == 0
    assert len(plate_map) == 96
    per_solute = plate_map.groupby("solute")["role"].value_counts().unstack()
    assert (per_solute["control"] == 1).all() and (per_solute["sample"] == campaign.N_CONDITIONS).all()
    dispensed = plate_map[plate_map.role == "sample"][space.GREEN_FRACTION_COLUMNS].drop_duplicates()
    assert len(dispensed) == campaign.N_CONDITIONS  # every condition dispensed as a distinct mixture


def test_bo_bridge_merge_reads_reduced_debug_spectra_and_sdl_bo_reads_the_result(tmp_path):
    plate_map = OT_EXAMPLES / f"plate_map_round{R0}.csv"
    readers = [DEBUG_DIR / f"reader_round{R0}_plate{i}.csv" for i in range(P, P + 3)]
    reduce = subprocess.run([sys.executable, "-m", "analysis", "reduce", "--plate-map", str(plate_map), "--reader", *map(str, readers),
                             "--blank", str(DEBUG_DIR / f"reader_round{R0}_blank.csv"), "--outdir", str(tmp_path)],
                            capture_output=True, text=True, cwd=REPO)
    assert reduce.returncode == 0, reduce.stdout + reduce.stderr
    endpoints = [tmp_path / f"endpoint_round{R0}_plate{i}.csv" for i in range(P, P + 3)]
    dataset_path = tmp_path / "bo_dataset.csv"
    result = run_bridge("merge", "--plate-map", plate_map, "--reader", *endpoints, "--blank", tmp_path / f"endpoint_round{R0}_blank.csv",
                        "--dataset", dataset_path, "--wells-out", tmp_path / "wells.csv")
    assert result.returncode == 0, result.stdout + result.stderr
    raw = pd.read_csv(dataset_path)
    assert len(raw) == 96 and (raw["n_obs"] == 3).all()  # 4 solutes x 24 conditions, 3 plates pooled
    assert set(pd.read_csv(tmp_path / "wells.csv")["plate"]) == set(range(P, P + 3))
    df = dataset.load_dataset(dataset_path)  # every solute was read at its own band, so all blocks are meaningful
    assert df.groupby("solute").size().eq(campaign.N_CONDITIONS).all() and df["rel_mean"].between(0, 1.2).all()


def test_one_closed_loop_round_end_to_end(tmp_path, coarse_grid):
    from make_examples import run_campaign
    dataset_path = run_campaign(1, tmp_path, tmp_path, seed=0)
    next_path = tmp_path / f"suggestions_round{R0 + 1}.csv"
    next_rows = pd.read_csv(next_path)
    assert len(next_rows) == campaign.N_CONDITIONS
    assert next_rows["condition_id"].str.match(rf"R{R0 + 1}_(exploit|explore)\d\d|R{R0}_seed\d\d").all()
    result = run_bridge("layout", "--round", R0 + 1, "--suggestions", next_path, "--outdir", tmp_path / "next")
    assert result.returncode == 0, result.stdout + result.stderr
    assert dataset.next_round_number(dataset.load_dataset(dataset_path)) == R0 + 1



def test_bo_bridge_grid_and_layout_respect_forbidden_pairs(tmp_path):
    result = run_bridge("grid", "--round", R0, "-o", tmp_path / "grid.csv")
    assert result.returncode == 0, result.stdout + result.stderr
    grid = pd.read_csv(tmp_path / "grid.csv")
    used = grid[space.GREEN_FRACTION_COLUMNS].gt(0)
    assert all(config.is_allowed([c[len("frac_"):] for c in used.columns[row]]) for row in used.to_numpy())
    if config.FORBIDDEN_PAIRS:
        a, b = sorted(next(iter(config.FORBIDDEN_PAIRS)))
        bad = pd.DataFrame({"condition_id": ["bad"], f"frac_{a}": [0.5], f"frac_{b}": [0.5]})
        bad.to_csv(tmp_path / "bad.csv", index=False)
        result = run_bridge("layout", "--round", R0, "--suggestions", tmp_path / "bad.csv", "--outdir", tmp_path / "bad")
        assert result.returncode != 0 and "forbidden" in result.stdout + result.stderr


def test_layout_warns_but_succeeds_when_a_solvent_exceeds_its_trough(tmp_path):
    """Production has no solvent cap (limit_solvent_to_trough = false): layout says to add troughs instead of failing."""
    assert not config.LIMIT_SOLVENT_TO_TROUGH
    suggestions = tmp_path / "suggestions.csv"
    rows = [{"condition_id": f"R0_x{i:02d}", **{f"frac_{s}": float(s == "acetone") for s in config.GREEN_SOLVENTS}} for i in range(23)]
    pd.DataFrame(rows).to_csv(suggestions, index=False)  # 23 conditions of pure acetone: far more than one trough
    result = run_bridge("layout", "--round", R0, "--suggestions", suggestions, "--outdir", tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TOO MUCH" in result.stdout and "WARNING" in result.stdout and (tmp_path / f"ot_input_round{R0}.csv").exists()
