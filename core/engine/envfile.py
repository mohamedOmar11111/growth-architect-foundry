"""growth_engine.envfile: `.env` and YAML-frontmatter readers that work with only the
standard library, so the read-only commands run in minimal sandboxes (for example
ChatGPT's code interpreter) where python-dotenv / PyYAML may be missing.

When the real packages are installed they are used unchanged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

try:
    from dotenv import dotenv_values as _dotenv_values
except ImportError:  # pragma: no cover - exercised by the stdlib-only test
    _dotenv_values = None

try:
    import yaml as _yaml
except ImportError:  # pragma: no cover - exercised by the stdlib-only test
    _yaml = None

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _parse_env_line(line: str) -> tuple[str, str | None] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export "):].lstrip()
    key, sep, value = line.partition("=")
    key = key.strip()
    if not _KEY_RE.match(key):
        return None
    if not sep:
        return key, None
    value = value.strip()
    if value[:1] in ("'", '"'):
        end = value.find(value[0], 1)
        value = value[1:end] if end != -1 else value[1:]
    else:
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
    return key, value


def dotenv_values(path: str | Path) -> dict[str, str | None]:
    """Same contract as python-dotenv's dotenv_values (no ${VAR} interpolation in the fallback)."""
    if _dotenv_values is not None:
        return dict(_dotenv_values(path))
    values: dict[str, str | None] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed:
            values[parsed[0]] = parsed[1]
    return values


def _scalar(text: str) -> object:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "~", ""):
        return None
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


class _FlatYaml:
    """Stand-in for the two PyYAML calls the engine makes, for flat frontmatter only.
    Real PyYAML is used whenever it is installed; this just keeps read paths working."""

    @staticmethod
    def safe_load(text: str) -> dict:
        return load_frontmatter(text)

    @staticmethod
    def safe_dump(data: dict, sort_keys: bool = False) -> str:
        items = sorted(data.items()) if sort_keys else data.items()
        return "".join(f"{key}: {json.dumps(value, default=str, ensure_ascii=False)}\n"
                       for key, value in items)


yaml = _yaml if _yaml is not None else _FlatYaml()


def load_frontmatter(block: str) -> dict:
    """Parse the YAML block between the `---` fences of a signal/task file.
    PyYAML when available; otherwise a flat `key: value` reader (these files are flat)."""
    if _yaml is not None:
        return _yaml.safe_load(block) or {}
    meta: dict[str, object] = {}
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or line.startswith((" ", "\t", "-")):
            continue
        key, sep, value = line.partition(":")
        if sep and _KEY_RE.match(key.strip()):
            meta[key.strip()] = _scalar(value)
    return meta
