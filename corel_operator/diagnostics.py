"""Run static or connection-enabled CorelDRAW X7 diagnostics."""
from __future__ import annotations

import argparse
import json
import platform
import struct
from importlib import metadata
from typing import Any

from .adapters import CorelX7Adapter
from .corel_bridge import CorelBridge
from .errors import CorelBridgeError
from .version import BRIDGE_VERSION, TOOL_SCHEMA_VERSION


def _distribution_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _registered_value(path: str) -> str | None:
    if platform.system() != "Windows":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, path) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return str(value)
    except (FileNotFoundError, OSError):
        return None


def collect_static_diagnostics() -> dict[str, Any]:
    adapter = CorelX7Adapter()
    registrations = {
        prog_id: {
            "registered": _registered_value(prog_id + "\\CLSID") is not None,
            "clsid": _registered_value(prog_id + "\\CLSID"),
        }
        for prog_id in adapter.PROG_IDS
    }
    registrations[adapter.GENERIC_PROG_ID]["current_version"] = _registered_value(
        adapter.GENERIC_PROG_ID + "\\CurVer"
    )
    return {
        "bridge_version": BRIDGE_VERSION,
        "tool_schema_version": TOOL_SCHEMA_VERSION,
        "profile": adapter.profile_summary(),
        "platform": platform.platform(),
        "windows": platform.system() == "Windows",
        "python_version": platform.python_version(),
        "python_bitness": struct.calcsize("P") * 8,
        "mcp_sdk_version": _distribution_version("mcp"),
        "pywin32_version": _distribution_version("pywin32"),
        "com_registrations": registrations,
        "connection_attempted": False,
    }


def run_diagnostics(connect: bool = True) -> dict[str, Any]:
    report = collect_static_diagnostics()
    if not connect:
        return report
    report["connection_attempted"] = True
    bridge = CorelBridge()
    try:
        report["coreldraw"] = bridge.connect()
        report["com_connection"] = "success"
    except CorelBridgeError as exc:
        report["com_connection"] = "failed"
        report["error"] = {
            "code": exc.code.value,
            "message": str(exc),
            "details": exc.details,
        }
        report["next_step"] = (
            "Open CorelDRAW X7, check the registered version, install requirements, and rerun. "
            "Do not send credentials, serial numbers, or client files."
        )
    except Exception as exc:
        report["com_connection"] = "failed"
        report["error"] = {
            "code": "INTERNAL_ERROR",
            "message": "Unexpected diagnostic failure.",
            "details": {"exception_type": type(exc).__name__},
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Inspect runtime/profile/COM registration without attaching to or launching CorelDRAW.",
    )
    args = parser.parse_args()
    print(json.dumps(run_diagnostics(connect=not args.static_only), indent=2, default=str))


if __name__ == "__main__":
    main()
