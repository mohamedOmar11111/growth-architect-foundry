"""Regression tests for red-team findings (budget-cap bypass, tenant aliasing/symlinks)."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from commands import live


def _tenant(tmp_path):
    reports = tmp_path / "04_Reports"
    reports.mkdir(exist_ok=True)
    env = {"META_ACCESS_TOKEN": "t", "META_AD_ACCOUNT_ID": "1"}
    return SimpleNamespace(name="T", env=env, reports_dir=reports,
                           require=lambda *k: tuple(env[x] for x in k))


@pytest.mark.parametrize("bad", ["nan", "NaN", "inf", "-inf", "-5", "0", "1e999"])
def test_budget_rejects_non_finite_and_non_positive(tmp_path, bad):
    camps = {"meta:1": {"name": "c", "budget": 100.0, "platform": "meta"}}
    with patch.object(live, "_meta_update_budget") as write:
        rc = live._cmd_budget(_tenant(tmp_path), camps,
                              {"campaign_id": "meta:1", "new_budget": bad, "confirm": True})
    assert rc == 2 and not write.called


@pytest.mark.parametrize("current", [0.0, -1.0])
def test_budget_fails_closed_when_baseline_unknown(tmp_path, current):
    camps = {"meta:1": {"name": "c", "budget": current, "platform": "meta"}}
    with patch.object(live, "_meta_update_budget") as write:
        rc = live._cmd_budget(_tenant(tmp_path), camps,
                              {"campaign_id": "meta:1", "new_budget": 1e9, "confirm": True})
    assert rc == 2 and not write.called


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("FOUNDRY_WORKSPACE", str(tmp_path))
    import paths
    importlib.reload(paths)
    import tenant
    importlib.reload(tenant)
    clients = tmp_path / "02_Active_Clients"
    good = clients / "Good"
    good.mkdir(parents=True)
    (good / ".env").write_text("OPERATOR_NAME=x\n")
    (good / "STRATEGY.md").write_text("ok")
    yield tenant, clients, tmp_path
    monkeypatch.delenv("FOUNDRY_WORKSPACE")
    importlib.reload(paths)
    importlib.reload(tenant)


@pytest.mark.parametrize("alias", ["good", "Good.", "Good ", "GOOD", "../Good", "Good/../Good"])
def test_tenant_name_must_match_exactly(workspace, alias):
    tenant, _, _ = workspace
    with pytest.raises(tenant.TenantConfigError):
        tenant.TenantContext(alias)


def test_tenant_loads_with_exact_name(workspace):
    tenant, _, _ = workspace
    assert tenant.TenantContext("Good").name == "Good"


def _symlink(target, link):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this system")


def test_symlinked_strategy_is_refused(workspace):
    tenant, clients, root = workspace
    secret = root / "secret.txt"
    secret.write_text("TOP-SECRET")
    evil = clients / "Evil"
    evil.mkdir()
    (evil / ".env").write_text("OPERATOR_NAME=x\n")
    _symlink(secret, evil / "STRATEGY.md")
    with pytest.raises(tenant.TenantConfigError):
        tenant.TenantContext("Evil")


def test_symlinked_env_is_refused(workspace):
    tenant, clients, _ = workspace
    evil = clients / "Evil"
    evil.mkdir()
    (evil / "STRATEGY.md").write_text("ok")
    _symlink(clients / "Good" / ".env", evil / ".env")
    with pytest.raises(tenant.TenantConfigError):
        tenant.TenantContext("Evil")


def test_symlinked_tenant_dir_is_refused(workspace):
    tenant, clients, _ = workspace
    _symlink(clients / "Good", clients / "Alias")
    with pytest.raises(tenant.TenantConfigError):
        tenant.TenantContext("Alias")


@pytest.mark.parametrize("name", ["CON", "nul", "Aux", "COM1", "lpt9"])
def test_setup_rejects_windows_device_names(name, tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("FOUNDRY_WORKSPACE", str(tmp_path))
    import paths
    importlib.reload(paths)
    import commands.setup as setup
    importlib.reload(setup)
    assert setup.cmd_init({"client": name}) == 2
    monkeypatch.delenv("FOUNDRY_WORKSPACE")
    importlib.reload(paths)
