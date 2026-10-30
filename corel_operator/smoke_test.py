"""Creates a separate test document, adds editable sample objects, and saves to a new CDR file."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
from .corel_bridge import CorelBridge


def main() -> None:
    bridge = CorelBridge()
    connection = bridge.connect()
    print("Connected:", json.dumps(connection, indent=2, default=str))

    # Create a new document, never modify the document that was already open.
    result = bridge.create_document(8.5, 11.0)
    print("Created test document:", json.dumps(result, indent=2))

    bridge.draw_rectangle(1.0, 8.5, 6.5, 1.3)
    bridge.add_text("CORELDRAW AI OPERATOR", 1.2, 9.0, 22, "Arial", True)
    bridge.add_text("X7 COM smoke test - editable text and shapes", 1.2, 8.0, 12, "Arial", False)

    out_dir = Path.home() / "Documents" / "CorelDRAW-AI-Operator-Tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"CorelOperator-SmokeTest-{stamp}.cdr"
    print(json.dumps(bridge.save_document(str(out_path)), indent=2))
    print("\nTEST CREATED. Open the saved CDR and confirm you see a rectangle and editable text.")
    print("File:", out_path)


if __name__ == "__main__":
    main()
