"""Every workflow must be valid YAML with least-privilege permissions and SHA-pinned actions.
(A broken workflow file only shows up as a confusing failed run on GitHub.)"""
import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_parses_and_is_hardened(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc and "jobs" in doc and (True in doc or "on" in doc)     # YAML reads `on:` as True
    assert doc.get("permissions"), f"{path.name} needs a top-level permissions block"
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.search(r"uses:\s*([^\s@]+)@(\S+)", line)
        if match:
            assert re.fullmatch(r"[0-9a-f]{40}", match.group(2)), f"unpinned action: {line.strip()}"
