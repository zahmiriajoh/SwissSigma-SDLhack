"""The seams: bo_bridge.py <-> SDL_BO <-> fake plate reader. bo_bridge is run as the real script."""
import pandas as pd
import pytest

from SDL_BO import campaign, dataset, space
from conftest import DEBUG_DIR, OT_EXAMPLES, load_bo_bridge, run_bridge


def test_sdl_bo_constants_mirror_bo_bridge():
    bridge = load_bo_bridge()
    assert space.ALL_SOLVENTS == bridge.ALL_SOLVENTS
    assert space.REFERENCE_SOLVENT == bridge.REFERENCE_SOLVENT
    assert space.TOTAL_UL == bridge.TOTAL_UL and space.MIN_UL == bridge.MIN_UL
    assert space.MAX_SOLVENTS_PER_MIXTURE == bridge.MAX_SOLVENTS_PER_MIX
    assert space.TROUGH_USABLE_UL == bridge.TROUGH_USABLE_UL and space.N_PLATES == bridge.N_PLATES
    assert space.N_SOLUTES == len(bridge.SOLUTES)
    assert campaign.N_CONDITIONS == (len(bridge.PLATE_WELLS) // len(bridge.SOLUTES) - bridge.CONTROLS_PER_SOLUTE)
    assert space.FRACTION_COLUMNS == bridge.FRAC_COLS


def test_fake_plate_reader_names_mirror_bo_bridge():
    import fake_plate_reader as fpr
    bridge = load_bo_bridge()
    assert fpr.ALL_SOLVENTS == bridge.ALL_SOLVENTS and list(fpr.PEAK_NM) == bridge.SOLUTES


def test_bo_bridge_layout_accepts_seed_design(tmp_path):
    suggestions = tmp_path / "suggestions_round1.csv"
    campaign.seed_design().to_csv(suggestions, index=False)
    result = run_bridge("layout", "--round", 1, "--suggestions", suggestions, "--outdir", tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "snapped" not in result.stdout  # 5 uL grid: nothing gets rounded
    plate_map = pd.read_csv(tmp_path / "plate_map_round1.csv")
    assert len(plate_map) == 96
    per_solute = plate_map.groupby("solute")["role"].value_counts().unstack()
    assert (per_solute["control"] == 1).all() and (per_solute["sample"] == campaign.N_CONDITIONS).all()
    dispensed = plate_map[plate_map.role == "sample"][space.GREEN_FRACTION_COLUMNS].drop_duplicates()
    assert len(dispensed) == campaign.N_CONDITIONS  # every condition dispensed as a distinct mixture


def test_bo_bridge_merge_reads_debug_spectra_and_sdl_bo_reads_the_result(tmp_path):
    readers = [DEBUG_DIR / f"reader_round1_plate{i}.csv" for i in (1, 2, 3)]
    dataset_path = tmp_path / "bo_dataset.csv"
    result = run_bridge("merge", "--plate-map", OT_EXAMPLES / "plate_map_round1.csv", "--reader", *readers,
                        "--blank", DEBUG_DIR / "reader_round1_blank.csv", "--wavelength", 275,
                        "--dataset", dataset_path, "--wells-out", tmp_path / "wells.csv")
    assert result.returncode == 0, result.stdout + result.stderr
    raw = pd.read_csv(dataset_path)
    assert len(raw) == 96 and (raw["n_obs"] == 3).all()  # 4 solutes x 24 conditions, 3 plates pooled
    with pytest.warns(UserWarning, match="negative rel_mean"):  # other solutes read off-band at 275 nm
        df = dataset.load_dataset(dataset_path)
    s1 = df[df.solute == "S1"]  # 275 nm is S1's band, so S1 is the meaningful block here
    assert len(s1) == campaign.N_CONDITIONS and s1["rel_mean"].between(0, 1.2).all()


def test_one_closed_loop_round_end_to_end(tmp_path, coarse_grid):
    from make_examples import run_campaign
    dataset_path = run_campaign(1, tmp_path, tmp_path, seed=0)
    assert (tmp_path / "suggestions_round2.csv").exists()
    next_rows = pd.read_csv(tmp_path / "suggestions_round2.csv")
    assert len(next_rows) == campaign.N_CONDITIONS
    result = run_bridge("layout", "--round", 2, "--suggestions", tmp_path / "suggestions_round2.csv",
                        "--outdir", tmp_path / "round2")
    assert result.returncode == 0, result.stdout + result.stderr
    assert dataset.next_round_number(dataset.load_dataset(dataset_path)) == 2

