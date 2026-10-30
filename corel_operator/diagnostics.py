"""Run local CorelDRAW X7 connection diagnostics."""
import json
import platform
import sys
from .corel_bridge import CorelBridge


def main() -> None:
    report = {
        "platform": platform.platform(),
        "python": sys.version,
        "windows": platform.system() == "Windows",
    }
    bridge = CorelBridge()
    try:
        report["coreldraw"] = bridge.connect()
        report["com_connection"] = "success"
    except Exception as exc:
        report["com_connection"] = "failed"
        report["error"] = str(exc)
        report["next_step"] = (
            "Open CorelDRAW, check the installed version, install requirements, and rerun. "
            "Do not send credentials, serial numbers, or client files."
        )
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
