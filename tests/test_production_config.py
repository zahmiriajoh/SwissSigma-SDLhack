"""production/config.toml is consistent and exposes what the pipeline needs."""
import pytest

from conftest import REPO
from production import config


def test_values_from_the_user():
    assert config.SOLUTES == ["Glutarimide", "Boc-hydroxyproline", "Phthalimide", "Succinimide"]
    assert config.ALL_SOLVENTS == ["DMF", "acetone", "EtOH", "iPrOH", "water", "iPrOAc", "tBuOAc"]
    assert config.REFERENCE_SOLVENT == "DMF" and config.GREEN_SOLVENTS[0] == "acetone"
    assert config.SOLVENT_LABELS["iPrOAc"] == "i-PrOAc"
    assert config.TOTAL_UL == 300 and config.MIN_UL == 5 and config.N_PLATES == 3
    assert (config.FIRST_ROUND, config.FIRST_PLATE, config.FIRST_CONDITION) == (0, 0, 1)
    assert config.MAX_SOLVENTS_PER_MIX == config.MAX_SOLVENTS_PER_MIXTURE == 3
    assert all(v is None for v in config.SOLUTE_WAVELENGTH_NM.values())  # unknown until measured


def test_troughs_and_identifiers():
    troughs = [t for v in config.SOLVENT_TROUGHS.values() for t in v]
    assert len(set(troughs)) == len(troughs)
    assert all("-" not in s and " " not in s for s in config.ALL_SOLVENTS)
    assert set(config.PLATE_ATTACKERS) == {"DMF", "acetone", "iPrOAc", "tBuOAc"}


def test_loader_rejects_inconsistent_files(tmp_path):
    text = (REPO / "production" / "config.toml").read_text()
    bad = tmp_path / "bad.toml"
    bad.write_text(text.replace('trough = "B1"', 'trough = "A1"'))  # acetone shares DMF's trough
    with pytest.raises(ValueError, match="share a trough"):
        config.load(bad)
    bad.write_text(text.replace('name = "iPrOH"', 'name = "i-PrOH"'))
    with pytest.raises(ValueError, match="hyphens"):
        config.load(bad)


def test_forbidden_pairs():
    assert config.FORBIDDEN_PAIRS == [frozenset({"water", "iPrOAc"}), frozenset({"water", "tBuOAc"})]
    assert config.is_allowed(["water", "EtOH"]) and config.is_allowed(["iPrOAc", "tBuOAc", "acetone"])
    assert not config.is_allowed(["water", "iPrOAc"]) and not config.is_allowed(["EtOH", "tBuOAc", "water"])


def test_a_solvent_may_have_several_troughs(tmp_path):
    text = config.CONFIG_PATH.read_text().replace('trough = "B1"', 'trough = ["B1", "H1"]')
    path = tmp_path / "config.toml"
    path.write_text(text)
    assert config._as_list(config.load(path)["solvents"][1]["trough"]) == ["B1", "H1"]
    with pytest.raises(ValueError, match="share a trough"):
        path.write_text(config.CONFIG_PATH.read_text().replace('trough = "B1"', 'trough = ["B1", "C1"]'))  # C1 is EtOH's
        config.load(path)
