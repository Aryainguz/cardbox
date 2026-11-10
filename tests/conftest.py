import pytest


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    """Every test gets its own empty workspace."""
    monkeypatch.setenv("CARDBOX_HOME", str(tmp_path / "home"))
    return tmp_path / "home"
