"""Shared in-process workspace builder for the test_cov_* modules (no subprocess, no real workspace)."""
from pathlib import Path

PLACEHOLDER_ENV = "OPERATOR_NAME=Your Name\nGOOGLE_ADS_CLIENT_ID=your_id_here\n"
CSV = ("Campaign name,Delivery,Results,Impressions,Clicks (all),Amount spent (USD)\n"
       "KSA_Prospecting,active,52,50000,2500,500\nUAE_Retargeting,active,6,30000,600,300\n"
       "EGY_Broad,active,0,20000,100,200\n")


def patch_workspace(monkeypatch, root: Path) -> Path:
    """Point every module that bound a path at import time to `root`; returns the clients dir."""
    import tenant, utils, paths, root_bus
    from commands import tenants
    from commands import state
    from loops import lead_qualify
    clients = root / "02_Active_Clients"
    clients.mkdir(parents=True, exist_ok=True)
    for mod, attrs in {
        tenant: {"CLIENTS_ROOT": clients}, tenants: {"CLIENTS_ROOT": clients},
        utils: {"WORKSPACE": root, "LOG_PATH": root / "log.md"}, state: {"LOG_PATH": root / "log.md"},
        paths: {"WORKSPACE": root},
        root_bus: {"HQ_ROOT": root, "CLIENTS_ROOT": clients, "SIGNALS_DIR": root / "signals",
                   "TASKS_DIR": root / "tasks", "LOG_PATH": root / "log.md"},
        lead_qualify: {"DOMAIN_ROOT": root / "domain" / "lead-qualify",
                       "DRAFTS_DIR": root / "domain" / "lead-qualify" / "drafts",
                       "STATE_PATH": root / "domain" / "lead-qualify" / "STATE.md"},
    }.items():
        for k, v in attrs.items():
            monkeypatch.setattr(mod, k, v)
    return clients


def make_tenant(monkeypatch, tmp_path, name="Acme", env=PLACEHOLDER_ENV, strategy="# Strategy\n"):
    clients = patch_workspace(monkeypatch, tmp_path)
    root = clients / name
    root.mkdir(exist_ok=True)
    (root / ".env").write_text(env, encoding="utf-8")
    (root / "STRATEGY.md").write_text(strategy, encoding="utf-8")
    from tenant import TenantContext
    return TenantContext(name)


def import_csv(tenant, tmp_path, text=CSV):
    from commands import campaigns
    f = tmp_path / "export.csv"
    f.write_text(text, encoding="utf-8")
    assert campaigns.run(tenant, {"verb": "import", "file": str(f)}) == 0
