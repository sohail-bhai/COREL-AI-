"""Safe 4-Up Imposition of PRINT PACKAGING.cdr on standard 25x19 sheet."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pythoncom
from corel_operator.corel_bridge import CorelBridge
from corel_operator.imposition import optimize_sheet_layout


def run_packaging_4up_imposition() -> dict[str, any]:
    pythoncom.CoInitialize()
    bridge = CorelBridge()
    bridge.connect()
    app = bridge.app

    source_path = Path(r"c:\Users\ADMIN\Desktop\VARUN\PRINT PACKAGING.cdr")
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    cdr_output = output_dir / "PRINT_PACKAGING_4UP_25x19.cdr"
    pdf_output = output_dir / "PRINT_PACKAGING_4UP_25x19.pdf"

    if cdr_output.exists():
        cdr_output.unlink()
    if pdf_output.exists():
        pdf_output.unlink()

    print("[1/6] Opening source file READ-ONLY to measure and copy content...")
    # Open source document strictly read-only
    doc_source = app.OpenDocument(str(source_path))
    doc_target = None

    try:
        with bridge._in_inches(doc_source):
            page_w = doc_source.ActivePage.SizeWidth
            page_h = doc_source.ActivePage.SizeHeight
            all_shapes = doc_source.ActivePage.Shapes.All()
            art_w = all_shapes.SizeWidth
            art_h = all_shapes.SizeHeight
            print(f"      Source Page Dimensions: {page_w:.3f} x {page_h:.3f} inches")
            print(f"      Source Artwork Bounds:  {art_w:.4f} x {art_h:.4f} inches")
            print(f"      Source Shapes Count:    {doc_source.ActivePage.Shapes.Count}")

            print("[2/6] Copying all artwork shapes to clipboard...")
            all_shapes.Copy()

        # Immediately close the original file to ensure documentation & file integrity
        doc_source.Close()
        doc_source = None
        print("      SUCCESS: Source document closed cleanly WITHOUT any modifications.")

        # Imposition geometry calculation
        sheet_w = 25.0
        sheet_h = 19.0
        gutter = 0.25  # 1/4 inch guillotine cut channel

        # Symmetrical centering of 2x2 grid
        grid_total_w = (art_w * 2) + gutter
        grid_total_h = (art_h * 2) + gutter
        margin_x = round((sheet_w - grid_total_w) / 2.0, 4)
        margin_y = round((sheet_h - grid_total_h) / 2.0, 4)

        col_x = [margin_x, margin_x + art_w + gutter]
        row_y = [margin_y, margin_y + art_h + gutter]

        print(f"[3/6] Imposition calculations for 4-up on standard {sheet_w} x {sheet_h} in sheet:")
        print(f"      Layout: 2 columns x 2 rows (Upright, no rotation needed)")
        print(f"      Left/Right Margins: {margin_x:.3f} inches")
        print(f"      Top/Bottom Margins: {margin_y:.3f} inches")
        print(f"      Center Cutting Gutters: {gutter:.3f} inches")
        print(f"      Paper Utilization: {((art_w * art_h * 4) / (sheet_w * sheet_h)) * 100:.1f}%")

        # Create new target document
        print(f"[4/6] Creating brand new production sheet ({sheet_w} x {sheet_h} in)...")
        doc_target = app.CreateDocument()
        with bridge._in_inches(doc_target):
            doc_target.ActivePage.SetSize(sheet_w, sheet_h)

            # Paste first unit
            doc_target.ActiveLayer.Paste()
            pasted_sr = doc_target.SelectionRange
            unit_1 = pasted_sr.Group()
            unit_1.Name = "Packaging_Unit_01"

            # Duplicate for remaining 3 units
            unit_2 = unit_1.Duplicate(0.0, 0.0)
            unit_2.Name = "Packaging_Unit_02"

            unit_3 = unit_1.Duplicate(0.0, 0.0)
            unit_3.Name = "Packaging_Unit_03"

            unit_4 = unit_1.Duplicate(0.0, 0.0)
            unit_4.Name = "Packaging_Unit_04"

            # Set exact positions for all 4 units (CDR_BOTTOM_LEFT)
            with bridge._reference_point(doc_target, bridge.CDR_BOTTOM_LEFT):
                # Unit 1: Col 1, Row 2 (Top Left)
                unit_1.SetPosition(col_x[0], row_y[1])
                # Unit 2: Col 2, Row 2 (Top Right)
                unit_2.SetPosition(col_x[1], row_y[1])
                # Unit 3: Col 1, Row 1 (Bottom Left)
                unit_3.SetPosition(col_x[0], row_y[0])
                # Unit 4: Col 2, Row 1 (Bottom Right)
                unit_4.SetPosition(col_x[1], row_y[0])

            print("[5/6] Verified 4-up positions:")
            units = [unit_1, unit_2, unit_3, unit_4]
            labels = ["Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right"]
            for u, label in zip(units, labels):
                b = bridge._shape_bounds_inches(doc_target, u)
                print(f"      {u.Name} ({label}): pos=({b['x']:.3f}, {b['y']:.3f}) size={b['width']:.3f}x{b['height']:.3f}")

        # Bind target document to bridge for saving and exporting
        bridge.target_doc = doc_target
        print("[6/6] Saving imposed production CDR and exporting PDF...")
        bridge.save_document(str(cdr_output))
        bridge.export_pdf(str(pdf_output))

        print("\n" + "=" * 60)
        print("4-UP PACKAGING IMPOSITION COMPLETE!")
        print(f"Original File: UNTOUCHED & UNMODIFIED ({source_path.name})")
        print(f"New Sheet:     25.0 x 19.0 inches (Standard 19x25 Half-Sheet)")
        print(f"Imposed Units: 4 Units (2 x 2 Upright Grid)")
        print(f"Output CDR:    {cdr_output} ({cdr_output.stat().st_size:,} bytes)")
        print(f"Output PDF:    {pdf_output} ({pdf_output.stat().st_size:,} bytes)")
        print("=" * 60)

        return {
            "status": "SUCCESS",
            "sheet_width": sheet_w,
            "sheet_height": sheet_h,
            "art_width": art_w,
            "art_height": art_h,
            "cdr_path": str(cdr_output),
            "pdf_path": str(pdf_output),
        }

    finally:
        if doc_source is not None:
            try:
                doc_source.Close()
            except Exception:
                pass
        if doc_target is not None:
            try:
                doc_target.Close()
                print("Target document closed cleanly.")
            except Exception as e:
                print(f"Target close note: {e}")
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    run_packaging_4up_imposition()
