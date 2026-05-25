import pytest
from pydantic import ValidationError

from src.server_config.loader import load_spec
from src.server_config.models import Spec, RoleSpec, ChannelType


def test_load_valid_spec(real_spec_path):
    spec = load_spec(real_spec_path)
    assert isinstance(spec, Spec)
    assert spec.meta.spec_version == "1.0"
    assert spec.server.name == "Test Server"
    assert len(spec.roles) == 1
    assert spec.roles[0].id == "verified"
    assert spec.roles[0].color == "#2ECC71"
    assert len(spec.categories) == 1
    assert spec.categories[0].channels[0].type == ChannelType.text


def test_load_rejects_invalid_color(tmp_path, minimal_spec_yaml):
    bad = minimal_spec_yaml.replace('"#2ECC71"', '"not-a-color"')
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(ValidationError):
        load_spec(p)


def test_load_rejects_unknown_channel_type(tmp_path, minimal_spec_yaml):
    bad = minimal_spec_yaml.replace("type: text", "type: holographic")
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(ValidationError):
        load_spec(p)


def test_load_rejects_duplicate_role_ids(tmp_path, minimal_spec_yaml):
    bad = minimal_spec_yaml.replace(
        "roles:\n  - id: verified",
        "roles:\n  - id: verified\n    name: x\n    permissions: []\n  - id: verified",
    )
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(ValidationError):
        load_spec(p)


def test_load_real_spec_file():
    """The actual checked-in spec parses cleanly."""
    from pathlib import Path
    spec_path = Path(__file__).parent.parent.parent / "specs" / "server-spec.yaml"
    spec = load_spec(spec_path)
    assert spec.server.name  # not empty
    assert any(r.id == "lyceen_verifie" for r in spec.roles)
    assert any(c.id == "cat_accueil" for c in spec.categories)
