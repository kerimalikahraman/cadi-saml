"""Installation and runtime diagnostics for CADi SAML."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import shutil
from typing import Any, Dict, Optional


def _package_version(name: str) -> Optional[str]:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def environment_report() -> Dict[str, Any]:
    """Return a JSON-serializable report without failing on missing tools."""
    ccx_env = os.environ.get("CCX_BINARY") or os.environ.get("CALCULIX_EXE")
    ccx_path = ccx_env if ccx_env and os.path.isfile(ccx_env) else None
    ccx_path = ccx_path or shutil.which("ccx") or shutil.which("ccx.exe")
    dependencies = {}
    for name in ("numpy", "scipy", "gmsh", "cadquery-ocp", "pyyaml"):
        version = _package_version(name)
        dependencies[name] = {"installed": version is not None, "version": version}
    return {
        "cadi_saml_version": _package_version("cadi_saml") or "0.6.0",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": dependencies,
        "calculix": {
            "available": ccx_path is not None,
            "path": ccx_path,
            "source": "environment" if ccx_env and ccx_path else ("PATH" if ccx_path else None),
        },
    }


__all__ = ["environment_report"]
