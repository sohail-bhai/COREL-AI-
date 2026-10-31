"""Generate an intricate, high-aesthetic Synthwave Retro 80s album art design in CorelDRAW X7."""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pythoncom
from corel_operator.corel_bridge import CorelBridge


def build_synthwave_album() -> dict[str, any]:
    pythoncom.CoInitialize()
    bridge = CorelBridge()
    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    cdr_output = output_dir / "synthwave_album_art.cdr"
    pdf_output = output_dir / "synthwave_album_art.pdf"

    # Remove previous test files if present
    if cdr_output.exists():
        cdr_output.unlink()
    if pdf_output.exists():
        pdf_output.unlink()

    print("[1/8] Connecting to CorelDRAW X7...")
    status = bridge.connect()
    assert status["connected"] is True, "Could not connect to CorelDRAW"

    print("[2/8] Creating 8.5 x 8.5 inch square album canvas...")
    bridge.create_document(width_in=8.5, height_in=8.5)
    bridge.use_active_document(confirm_existing_document=True)
    doc = bridge.target_doc

    try:
        print("[3/8] Building cosmic sky & outer neon framing...")
        # 1. Base dark background
        bridge.draw_rectangle(0.0, 0.0, 8.5, 8.5, "Canvas_Cosmic_Base")
        bridge.set_fill_color(13, 2, 33, object_name="Canvas_Cosmic_Base")
        bridge.set_outline(0, 0, 0, width_points=0, object_name="Canvas_Cosmic_Base")

        # 2. Outer neon cyan border frame
        bridge.draw_rectangle(0.35, 0.35, 7.8, 7.8, "Neon_Border_Frame")
        bridge.set_outline(0, 245, 255, width_points=1.5, object_name="Neon_Border_Frame")

        # 3. Corner accent boxes (precisely aligned to the 7.8x7.8 frame corners)
        corners = [
            ("Corner_TL", 0.35, 7.90),
            ("Corner_TR", 7.90, 7.90),
            ("Corner_BL", 0.35, 0.35),
            ("Corner_BR", 7.90, 0.35),
        ]
        for name, cx, cy in corners:
            bridge.draw_rectangle(cx, cy, 0.25, 0.25, name)
            bridge.set_outline(255, 0, 127, width_points=1.0, object_name=name)

        print("[4/8] Constructing cyber perspective grid floor & glowing horizon...")
        # Deep violet floor
        bridge.draw_rectangle(0.35, 0.35, 7.8, 3.25, "Cyber_Floor_Base")
        bridge.set_fill_color(22, 10, 48, object_name="Cyber_Floor_Base")
        bridge.set_outline(0, 0, 0, width_points=0, object_name="Cyber_Floor_Base")

        # Perspective horizontal grid lines (spaced tighter near horizon)
        grid_y_coords = [3.55, 3.42, 3.26, 3.06, 2.80, 2.48, 2.08, 1.58, 0.98, 0.42]
        grid_line_names = []
        for i, gy in enumerate(grid_y_coords, 1):
            line_name = f"Grid_Line_H_{i}"
            h = 0.015 + (i * 0.003)
            bridge.draw_rectangle(0.35, gy, 7.8, h, line_name)
            bridge.set_fill_color(0, 245, 255, object_name=line_name)
            bridge.set_outline(0, 0, 0, width_points=0, object_name=line_name)
            grid_line_names.append(line_name)

        # Perspective vertical grid guide lines
        v_lines = [
            ("Grid_Line_V_Center", 4.24, 0.02),
            ("Grid_Line_V_Left1", 2.60, 0.015),
            ("Grid_Line_V_Right1", 5.88, 0.015),
            ("Grid_Line_V_Left2", 1.20, 0.015),
            ("Grid_Line_V_Right2", 7.28, 0.015),
        ]
        for vname, vx, vw in v_lines:
            bridge.draw_rectangle(vx, 0.35, vw, 3.25, vname)
            bridge.set_fill_color(0, 245, 255, object_name=vname)
            bridge.set_outline(0, 0, 0, width_points=0, object_name=vname)
            grid_line_names.append(vname)

        # Glowing Horizon Laser Bar
        bridge.draw_rectangle(0.35, 3.58, 7.8, 0.05, "Horizon_Glow_Outer")
        bridge.set_fill_color(255, 0, 127, object_name="Horizon_Glow_Outer")
        bridge.set_outline(0, 0, 0, width_points=0, object_name="Horizon_Glow_Outer")

        bridge.draw_rectangle(1.2, 3.595, 6.1, 0.02, "Horizon_Glow_Core")
        bridge.set_fill_color(255, 255, 255, object_name="Horizon_Glow_Core")
        bridge.set_outline(0, 0, 0, width_points=0, object_name="Horizon_Glow_Core")

        print("[5/8] Crafting iconic sliced 80s synthwave sunset...")
        # Outer halo ring
        bridge.draw_ellipse(2.35, 3.4, 3.8, 3.8, "Sun_Halo_Ring")
        bridge.set_outline(255, 0, 127, width_points=2.0, object_name="Sun_Halo_Ring")

        # Golden-Orange Sun disc
        bridge.draw_ellipse(2.55, 3.6, 3.4, 3.4, "Sun_Main_Disc")
        bridge.set_fill_color(255, 215, 0, object_name="Sun_Main_Disc")
        bridge.set_outline(0, 0, 0, width_points=0, object_name="Sun_Main_Disc")

        # Sliced scanline slits (matching background deep color)
        slits = [
            ("Sun_Slit_1", 2.45, 3.68, 3.6, 0.09),
            ("Sun_Slit_2", 2.50, 3.84, 3.5, 0.07),
            ("Sun_Slit_3", 2.55, 3.98, 3.4, 0.055),
            ("Sun_Slit_4", 2.65, 4.10, 3.2, 0.04),
            ("Sun_Slit_5", 2.75, 4.20, 3.0, 0.03),
            ("Sun_Slit_6", 2.85, 4.28, 2.8, 0.02),
            ("Sun_Slit_7", 3.00, 4.35, 2.5, 0.012),
        ]
        slit_names = []
        for sname, sx, sy, sw, sh in slits:
            bridge.draw_rectangle(sx, sy, sw, sh, sname)
            bridge.set_fill_color(13, 2, 33, object_name=sname)
            bridge.set_outline(0, 0, 0, width_points=0, object_name=sname)
            slit_names.append(sname)

        print("[6/8] Adding cyber typography & metallic chrome title...")
        # Top micro-header tags
        bridge.add_text("// SYNTHWAVE MASTER ARCHIVE", 0.6, 7.8, size_pt=9, font="Arial", bold=True, object_name="Header_Tag_Left")
        bridge.set_fill_color(0, 245, 255, object_name="Header_Tag_Left")

        bridge.add_text("STEREO [CAT. NO. SYN-1984]", 5.2, 7.8, size_pt=9, font="Arial", bold=True, object_name="Header_Tag_Right")
        bridge.set_fill_color(160, 220, 240, object_name="Header_Tag_Right")

        # Header accent separator
        bridge.draw_rectangle(0.6, 7.7, 7.3, 0.015, "Header_Divider")
        bridge.set_fill_color(0, 245, 255, object_name="Header_Divider")
        bridge.set_outline(0, 0, 0, width_points=0, object_name="Header_Divider")

        bridge.add_text("24-BIT / 96kHz ANALOG SYNTHESIS // DIRECT TAPE MASTER", 0.6, 7.45, size_pt=8, font="Arial", bold=False, object_name="Header_Subspec")
        bridge.set_fill_color(255, 0, 127, object_name="Header_Subspec")

        # Main Title Banner Plaque
        bridge.draw_rectangle(1.25, 2.15, 6.0, 1.15, "Title_Plaque_Bg")
        bridge.set_fill_color(10, 2, 25, object_name="Title_Plaque_Bg")
        bridge.set_outline(0, 245, 255, width_points=1.5, object_name="Title_Plaque_Bg")

        # Main Title: "NEON HORIZON" (Layered drop shadow + foreground)
        bridge.add_text("NEON HORIZON", 1.48, 2.68, size_pt=36, font="Arial", bold=True, object_name="Title_Shadow")
        bridge.set_fill_color(255, 0, 127, object_name="Title_Shadow")

        bridge.add_text("NEON HORIZON", 1.45, 2.72, size_pt=36, font="Arial", bold=True, object_name="Title_Foreground")
        bridge.set_fill_color(255, 255, 255, object_name="Title_Foreground")

        # Secondary subtitle
        bridge.add_text("— M I D N I G H T   D R I V E —", 2.25, 2.35, size_pt=13, font="Arial", bold=True, object_name="Title_Subtitle")
        bridge.set_fill_color(255, 230, 0, object_name="Title_Subtitle")

        print("[7/8] Adding footer tracklist, cassette specs, and vector barcode...")
        # Tracklist info badge
        bridge.draw_rectangle(0.6, 0.55, 3.0, 0.55, "Tracklist_Badge")
        bridge.set_fill_color(18, 5, 42, object_name="Tracklist_Badge")
        bridge.set_outline(0, 245, 255, width_points=1.0, object_name="Tracklist_Badge")

        bridge.add_text("SIDE A: 01. OUTRUN // 02. CYBERPULSE", 0.7, 0.82, size_pt=7.5, font="Arial", bold=True, object_name="Tracklist_Text")
        bridge.set_fill_color(255, 255, 255, object_name="Tracklist_Text")

        bridge.add_text("SYNTHESIS REC. // ALL RIGHTS RESERVED", 0.7, 0.65, size_pt=6.0, font="Arial", bold=False, object_name="Tracklist_Sub")
        bridge.set_fill_color(180, 180, 200, object_name="Tracklist_Sub")

        # Center gold record seal
        bridge.draw_ellipse(4.0, 0.58, 0.5, 0.5, "Record_Seal_Ring")
        bridge.set_fill_color(25, 15, 5, object_name="Record_Seal_Ring")
        bridge.set_outline(255, 215, 0, width_points=1.2, object_name="Record_Seal_Ring")

        bridge.add_text("84", 4.12, 0.70, size_pt=12, font="Arial", bold=True, object_name="Record_Seal_Text")
        bridge.set_fill_color(255, 215, 0, object_name="Record_Seal_Text")

        # Vector barcode lines (clean fills without thick stroke borders)
        bar_widths = [0.015, 0.04, 0.015, 0.025, 0.05, 0.015, 0.035, 0.015, 0.04, 0.025, 0.015, 0.05, 0.015, 0.035]
        bx = 6.0
        for b_idx, bw in enumerate(bar_widths, 1):
            b_name = f"Barcode_Bar_{b_idx}"
            bridge.draw_rectangle(bx, 0.62, bw, 0.45, b_name)
            bridge.set_fill_color(255, 255, 255, object_name=b_name)
            bridge.set_outline(0, 0, 0, width_points=0, object_name=b_name)
            bx += bw + 0.02

        bridge.add_text("8 49201 01984 2", 6.05, 0.50, size_pt=6.5, font="Arial", bold=False, object_name="Barcode_Number")
        bridge.set_fill_color(200, 200, 200, object_name="Barcode_Number")

        # Group components for clean production layering
        print("Grouping layers...")
        bridge.group_shapes(["Sun_Halo_Ring", "Sun_Main_Disc"] + slit_names, "Sunset_Sun_Group")
        bridge.group_shapes(["Title_Plaque_Bg", "Title_Shadow", "Title_Foreground", "Title_Subtitle"], "Album_Title_Group")

        # Align Title Group to page horizontal center
        bridge.align_to_page(["Album_Title_Group"], horizontal="center", align_as_group=True)

        print("[8/8] Saving CDR and exporting high-resolution PDF...")
        bridge.save_document(str(cdr_output))
        bridge.export_pdf(str(pdf_output))

        cdr_size = cdr_output.stat().st_size
        pdf_size = pdf_output.stat().st_size

        print("\n==================================================")
        print("SUCCESSFULLY GENERATED REFINED SYNTHWAVE ALBUM ART!")
        print(f"CDR File: {cdr_output} ({cdr_size:,} bytes)")
        print(f"PDF File: {pdf_output} ({pdf_size:,} bytes)")
        print("==================================================")

        return {
            "status": "SUCCESS",
            "cdr_path": str(cdr_output),
            "cdr_bytes": cdr_size,
            "pdf_path": str(pdf_output),
            "pdf_bytes": pdf_size,
        }

    finally:
        if doc is not None:
            try:
                doc.Close()
                print("Canvas closed cleanly.")
            except Exception as e:
                print(f"Close warning: {e}")
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    build_synthwave_album()
