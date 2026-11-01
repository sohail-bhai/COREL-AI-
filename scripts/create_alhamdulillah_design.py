"""Recreate the Islamic Alhamdulillah artwork in 100% native CorelDRAW vectors on A4 landscape."""
from __future__ import annotations

import math
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pythoncom
from PIL import Image
from corel_operator.corel_bridge import CorelBridge


def generate_moroccan_lattice_svg(out_path: Path, width_in: float, height_in: float, cols: int = 10, rows: int = 4) -> Path:
    """Generate a vector Moroccan quatrefoil / Islamic geometric lattice panel."""
    w_px = int(width_in * 72)
    h_px = int(height_in * 72)
    cell_w = w_px / cols
    cell_h = h_px / rows

    paths = []
    # Interlocking quatrefoil motifs
    for r in range(rows + 1):
        for c in range(cols + 1):
            cx = c * cell_w
            cy = r * cell_h
            rad = cell_w * 0.48
            # 4 interlocking arcs
            p = (
                f"M {cx - rad:.2f},{cy:.2f} "
                f"A {rad:.2f},{rad:.2f} 0 0 1 {cx:.2f},{cy - rad:.2f} "
                f"A {rad:.2f},{rad:.2f} 0 0 1 {cx + rad:.2f},{cy:.2f} "
                f"A {rad:.2f},{rad:.2f} 0 0 1 {cx:.2f},{cy + rad:.2f} "
                f"A {rad:.2f},{rad:.2f} 0 0 1 {cx - rad:.2f},{cy:.2f} Z"
            )
            paths.append(p)

            # Central diamond / star accent
            dr = rad * 0.35
            diamond = f"M {cx},{cy - dr:.2f} L {cx + dr:.2f},{cy} L {cx},{cy + dr:.2f} L {cx - dr:.2f},{cy} Z"
            paths.append(diamond)

    all_paths = " ".join(f'<path d="{p}"/>' for p in paths)
    svg_code = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w_px} {h_px}" width="{width_in}in" height="{height_in}in">
  <defs>
    <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#E8C888"/>
      <stop offset="50%" stop-color="#C59B52"/>
      <stop offset="100%" stop-color="#9C6F32"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#goldGrad)"/>
  <g fill="none" stroke="#68451D" stroke-width="0.8" opacity="0.85">
    {all_paths}
  </g>
</svg>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg_code, encoding="utf-8")
    return out_path


def generate_arch_frame_svg(out_path: Path, width_in: float, height_in: float) -> Path:
    """Generate an ornate Islamic multi-lobed / pointed Mihrab arch frame."""
    w = width_in * 72
    h = height_in * 72

    # Construct Islamic ogee / multi-lobed arch path
    # Bottom left (0, h) -> Up left wall (0, h*0.45) -> Stepped shoulder -> Pointed apex -> Down right
    sw = w * 0.08  # shoulder width
    sh = h * 0.35  # shoulder height
    mid_x = w * 0.5
    apex_y = h * 0.05
    shoulder_y = h * 0.40

    d = (
        f"M 0,{h} "
        f"L 0,{shoulder_y + sh} "
        f"Q 0,{shoulder_y} {sw},{shoulder_y} "
        f"L {sw * 1.5},{shoulder_y} "
        f"Q {sw * 2.0},{shoulder_y * 0.7} {mid_x * 0.6},{shoulder_y * 0.5} "
        f"Q {mid_x * 0.85},{shoulder_y * 0.25} {mid_x},{apex_y} "
        f"Q {w - (mid_x * 0.85)},{shoulder_y * 0.25} {w - (mid_x * 0.6)},{shoulder_y * 0.5} "
        f"Q {w - (sw * 2.0)},{shoulder_y * 0.7} {w - (sw * 1.5)},{shoulder_y} "
        f"L {w - sw},{shoulder_y} "
        f"Q {w},{shoulder_y} {w},{shoulder_y + sh} "
        f"L {w},{h} Z"
    )

    svg_code = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {h:.1f}" width="{width_in}in" height="{height_in}in">
  <defs>
    <radialGradient id="archBg" cx="50%" cy="40%" r="60%">
      <stop offset="0%" stop-color="#3D1B14"/>
      <stop offset="60%" stop-color="#260F0B"/>
      <stop offset="100%" stop-color="#180805"/>
    </radialGradient>
  </defs>
  <path d="{d}" fill="url(#archBg)" stroke="#D4AF37" stroke-width="2.0"/>
</svg>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg_code, encoding="utf-8")
    return out_path


def run_recreation() -> dict[str, any]:
    pythoncom.CoInitialize()
    bridge = CorelBridge()
    bridge.connect()
    app = bridge.app

    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    # A4 Landscape: 297mm x 210mm = 11.693 x 8.268 inches
    page_w = 11.693
    page_h = 8.268

    cdr_name = "test antigravity alhamdulilah.cdr"
    pdf_name = "test antigravity alhamdulilah.pdf"
    cdr_output = output_dir / cdr_name
    pdf_output = output_dir / pdf_name

    if cdr_output.exists():
        cdr_output.unlink()
    if pdf_output.exists():
        pdf_output.unlink()

    print("[1/8] Generating vector assets (calligraphy, lattice, arch)...")
    # 1. Calligraphy SVG
    calligraphy_svg = output_dir / "alhamdulillah_calligraphy.svg"
    if not calligraphy_svg.exists():
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_calligraphy_svg.py")], check=True)

    # 2. Lattice panels
    lattice_corner_svg = generate_moroccan_lattice_svg(output_dir / "lattice_corner.svg", 3.0, 2.5, cols=6, rows=5)
    lattice_bottom_svg = generate_moroccan_lattice_svg(output_dir / "lattice_bottom.svg", 10.7, 1.2, cols=22, rows=3)

    # 3. Arch frame
    arch_svg = generate_arch_frame_svg(output_dir / "mihrab_arch.svg", 9.8, 6.6)

    print("[2/8] Creating new A4 Landscape CorelDRAW document...")
    bridge.create_document(width_in=page_w, height_in=page_h)
    bridge.use_active_document(confirm_existing_document=True)
    doc = bridge.target_doc

    try:
        print("[3/8] Drawing rich base background & outer gold border...")
        # Deep mahogany background
        bridge.draw_rectangle(0.0, 0.0, page_w, page_h, "Canvas_Mahogany_Base")
        bridge.set_fill_color(42, 18, 14, object_name="Canvas_Mahogany_Base")
        bridge.set_outline(0, 0, 0, width_points=0, object_name="Canvas_Mahogany_Base")

        # Outer framing border
        bridge.draw_rectangle(0.35, 0.35, page_w - 0.70, page_h - 0.70, "Outer_Gold_Border")
        bridge.set_outline(212, 175, 55, width_points=1.5, object_name="Outer_Gold_Border")

        # Inset thin hairline frame
        bridge.draw_rectangle(0.42, 0.42, page_w - 0.84, page_h - 0.84, "Inner_Gold_Hairline")
        bridge.set_outline(235, 205, 130, width_points=0.5, object_name="Inner_Gold_Hairline")

        print("[4/8] Importing Moroccan geometric lattice panels...")
        # Top-Left corner lattice
        bridge.import_artwork(str(lattice_corner_svg), "Lattice_Top_Left")
        bridge.resize_object(width_inches=2.5, height_inches=2.2, object_name="Lattice_Top_Left")
        bridge.move_object(0.45, 5.65, object_name="Lattice_Top_Left")

        # Top-Right corner lattice
        bridge.import_artwork(str(lattice_corner_svg), "Lattice_Top_Right")
        bridge.resize_object(width_inches=2.5, height_inches=2.2, object_name="Lattice_Top_Right")
        bridge.move_object(page_w - 0.45 - 2.5, 5.65, object_name="Lattice_Top_Right")

        # Bottom horizontal lattice border band
        bridge.import_artwork(str(lattice_bottom_svg), "Lattice_Bottom_Band")
        bridge.resize_object(width_inches=page_w - 0.90, height_inches=1.1, object_name="Lattice_Bottom_Band")
        bridge.move_object(0.45, 0.45, object_name="Lattice_Bottom_Band")

        # Gold divider pinstripes flanking the bottom lattice band
        bridge.draw_rectangle(0.45, 1.57, page_w - 0.90, 0.02, "Divider_Bottom_Top")
        bridge.set_fill_color(225, 195, 130, object_name="Divider_Bottom_Top")
        bridge.set_outline(0, 0, 0, width_points=0, object_name="Divider_Bottom_Top")

        bridge.draw_rectangle(0.45, 0.43, page_w - 0.90, 0.02, "Divider_Bottom_Base")
        bridge.set_fill_color(225, 195, 130, object_name="Divider_Bottom_Base")
        bridge.set_outline(0, 0, 0, width_points=0, object_name="Divider_Bottom_Base")

        print("[5/8] Constructing central Mihrab arch silhouette...")
        bridge.import_artwork(str(arch_svg), "Mihrab_Arch_Panel")
        bridge.resize_object(width_inches=9.6, height_inches=6.4, object_name="Mihrab_Arch_Panel")
        bridge.move_object((page_w - 9.6) / 2.0, 1.58, object_name="Mihrab_Arch_Panel")

        print("[6/8] Adding celestial glowing bokeh orbs & flare sparkles...")
        # Golden bokeh flares
        flares = [
            ("Flare_Large_TR", 8.4, 6.7, 0.65, (255, 205, 90)),
            ("Flare_Core_TR", 8.55, 6.85, 0.35, (255, 240, 180)),
            ("Flare_Mid_TL", 3.4, 6.5, 0.40, (255, 195, 80)),
            ("Flare_Top_Mid", 6.8, 7.1, 0.30, (255, 215, 100)),
            ("Flare_Lower_R", 8.8, 2.7, 0.45, (255, 190, 80)),
            ("Flare_Small_1", 4.8, 6.8, 0.18, (255, 230, 130)),
            ("Flare_Small_2", 7.8, 5.8, 0.22, (255, 230, 130)),
        ]
        flare_names = []
        for fname, fx, fy, fsize, fcolor in flares:
            bridge.draw_ellipse(fx, fy, fsize, fsize, fname)
            bridge.set_fill_color(fcolor[0], fcolor[1], fcolor[2], object_name=fname)
            bridge.set_outline(0, 0, 0, width_points=0, object_name=fname)
            flare_names.append(fname)

        # 4-point sparkle star on calligraphy intersection
        # Cross bars
        bridge.draw_rectangle(7.75, 3.15, 0.02, 0.50, "Sparkle_V")
        bridge.set_fill_color(255, 255, 255, object_name="Sparkle_V")
        bridge.set_outline(255, 215, 0, width_points=0.5, object_name="Sparkle_V")

        bridge.draw_rectangle(7.51, 3.39, 0.50, 0.02, "Sparkle_H")
        bridge.set_fill_color(255, 255, 255, object_name="Sparkle_H")
        bridge.set_outline(255, 215, 0, width_points=0.5, object_name="Sparkle_H")

        # Center diamond glow
        bridge.draw_ellipse(7.71, 3.35, 0.10, 0.10, "Sparkle_Core")
        bridge.set_fill_color(255, 255, 255, object_name="Sparkle_Core")
        bridge.set_outline(0, 0, 0, width_points=0, object_name="Sparkle_Core")

        print("[7/8] Placing master Arabic Calligraphy & English typography...")
        # 1. Calligraphy Drop Shadow (espresso brown, shifted slightly)
        bridge.import_artwork(str(calligraphy_svg), "Calligraphy_Shadow")
        bridge.resize_object(width_inches=7.4, height_inches=4.2, object_name="Calligraphy_Shadow")
        cal_x = (page_w - 7.4) / 2.0
        cal_y = 2.65
        bridge.move_object(cal_x + 0.04, cal_y - 0.04, object_name="Calligraphy_Shadow")
        bridge.set_fill_color(18, 6, 4, object_name="Calligraphy_Shadow")
        bridge.set_outline(18, 6, 4, width_points=0.5, object_name="Calligraphy_Shadow")

        # 2. Calligraphy Foreground (Warm metallic gold)
        bridge.import_artwork(str(calligraphy_svg), "Calligraphy_Foreground")
        bridge.resize_object(width_inches=7.4, height_inches=4.2, object_name="Calligraphy_Foreground")
        bridge.move_object(cal_x, cal_y, object_name="Calligraphy_Foreground")
        bridge.set_fill_color(225, 195, 130, object_name="Calligraphy_Foreground")
        bridge.set_outline(195, 150, 75, width_points=0.75, object_name="Calligraphy_Foreground")

        # 3. English Typography: "Alhamdulillah"
        txt_res = bridge.add_text("Alhamdulillah", 3.2, 1.85, size_pt=38, font="Times New Roman", bold=True, object_name="Text_Alhamdulillah")
        bridge.set_fill_color(230, 205, 140, object_name="Text_Alhamdulillah")
        # Align text horizontally to page center
        bridge.align_to_page(["Text_Alhamdulillah"], horizontal="center")

        print("[8/8] Saving CDR and exporting high-resolution print PDF...")
        bridge.save_document(str(cdr_output))
        bridge.export_pdf(str(pdf_output))

        cdr_size = cdr_output.stat().st_size
        pdf_size = pdf_output.stat().st_size

        print("\n" + "=" * 65)
        print("ALHAMDULILLAH ARTWORK RECREATED SUCCESSFULLY IN VECTOR!")
        print(f"Format:        A4 Landscape ({page_w:.2f} x {page_h:.2f} inches / 297 x 210 mm)")
        print(f"CDR File:      {cdr_output} ({cdr_size:,} bytes)")
        print(f"PDF File:      {pdf_output} ({pdf_size:,} bytes)")
        print("Vector Layers: Mahogany Canvas, Gold Lattice Panels, Mihrab Arch,")
        print("               Bokeh Light Flares, Sparkle Stars, Arabic Calligraphy,")
        print("               and Centered Classical Serif English Typography.")
        print("=" * 65)

        return {
            "status": "SUCCESS",
            "page_width": page_w,
            "page_height": page_h,
            "cdr_path": str(cdr_output),
            "pdf_path": str(pdf_output),
        }

    finally:
        if doc is not None:
            try:
                doc.Close()
                print("Document closed cleanly.")
            except Exception as e:
                print(f"Close note: {e}")
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    run_recreation()
