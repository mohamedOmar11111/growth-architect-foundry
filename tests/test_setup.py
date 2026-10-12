"""setup init / doctor and the workspace-vs-engine path split."""
import importlib

import pytest


@pytest.fixture()
def setup_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_WORKSPACE", str(tmp_path))
    import paths
    importlib.reload(paths)
    import commands.setup as setup
    importlib.reload(setup)
    yield setup
    monkeypatch.delenv("FOUNDRY_WORKSPACE")
    importlib.reload(paths)


def test_workspace_comes_from_env_not_engine(tmp_path, setup_mod):
    import paths
    assert paths.WORKSPACE == tmp_path.resolve()
    assert paths.CLIENTS_ROOT == tmp_path.resolve() / "02_Active_Clients"
    assert paths.ENGINE_ROOT != paths.WORKSPACE


def test_init_creates_tenant_in_workspace_with_env_and_no_demo_signals(tmp_path, setup_mod):
    assert setup_mod.cmd_init({"client": "Acme_Store"}) == 0
    root = tmp_path / "02_Active_Clients" / "Acme_Store"
    assert (root / "STRATEGY.md").exists() and (root / ".env").exists()
    assert list((root / "signals").iterdir()) == []


def test_init_refuses_overwrite(tmp_path, setup_mod):
    assert setup_mod.cmd_init({"client": "Acme"}) == 0
    assert setup_mod.cmd_init({"client": "Acme"}) == 1


@pytest.mark.parametrize("bad", [None, "", "../evil", "a/b", "..", "/abs", "-x", "x" * 65])
def test_init_rejects_unsafe_names(tmp_path, setup_mod, bad):
    assert setup_mod.cmd_init({"client": bad}) == 2
    assert not (tmp_path / "02_Active_Clients").exists()


def test_doctor_reports_ok_and_lists_tenants(tmp_path, setup_mod, capsys):
    setup_mod.cmd_init({"client": "Acme"})
    assert setup_mod.cmd_doctor({}) == 0
    out = capsys.readouterr().out
    assert "Acme" in out and "python-dotenv" in out
