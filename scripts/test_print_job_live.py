"""Live end-to-end test of the print job imposition engine in CorelDRAW X7."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from pprint import pprint

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pythoncom
from corel_operator.corel_bridge import CorelBridge
from corel_operator.print_jobs import inspect_raster_artwork, plan_print_job


def create_sample_artwork(output_path: Path) -> Path:
    """Create a high-resolution 300 DPI vector-styled raster card (3.5 x 2.0 inches)."""
    # 3.5 in x 2.0 in at 300 DPI = 1050 x 600 px
    width_px = 1050
    height_px = 600
    img = Image.new("RGB", (width_px, height_px), (16, 20, 32))  # Deep midnight slate
    draw = ImageDraw.Draw(img)

    # Outer border & inner frame
    draw.rectangle([15, 15, width_px - 15, height_px - 15], outline=(0, 229, 255), width=4)
    draw.rectangle([25, 25, width_px - 25, height_px - 25], outline=(255, 0, 127), width=2)

    # Accent badge circle
    draw.ellipse([50, 150, 330, 430], fill=(30, 36, 56), outline=(0, 229, 255), width=4)
    draw.ellipse([90, 190, 290, 390], fill=(255, 0, 127), outline=(255, 215, 0), width=3)

    # Content typography
    draw.text((370, 160), "NOVA COFFEE ROASTERS", fill=(255, 255, 255))
    draw.text((370, 230), "SINGLE ORIGIN // ETHIOPIA GUJI", fill=(255, 215, 0))
    draw.text((370, 290), "GRADE 1 NATURAL | ELEVATION 2100M", fill=(180, 200, 220))
    draw.text((370, 350), "BATCH NO. #042 // NET WT 250G", fill=(0, 229, 255))
    draw.rectangle([370, 410, 980, 415], fill=(255, 0, 127))
    draw.text((370, 435), "CERTIFIED ORGANIC & DIRECT TRADE", fill=(140, 160, 180))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG", dpi=(300, 300))
    return output_path


def run_print_job_live_test() -> dict[str, any]:
    pythoncom.CoInitialize()
    bridge = CorelBridge()
    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    artwork_file = output_dir / "sample_business_card_300dpi.png"
    create_sample_artwork(artwork_file)
    print(f"[1/5] Created sample 300 DPI artwork: {artwork_file}")

    cdr_output = output_dir / "print_job_imposed_12x18.cdr"
    pdf_output = output_dir / "print_job_imposed_12x18.pdf"

    if cdr_output.exists():
        cdr_output.unlink()
    if pdf_output.exists():
        pdf_output.unlink()

    # Step 1: Artwork Inspection
    print("[2/5] Inspecting raster artwork metadata...")
    art_info = inspect_raster_artwork(str(artwork_file))
    print(f"      Dimensions: {art_info['width_pixels']} x {art_info['height_pixels']} px")
    print(f"      Color Mode: {art_info['mode']} ({art_info['color_space']})")
    print(f"      Resolution: {art_info['metadata_dpi']}")

    # Step 2: Imposition Planning for Small Card on Big 12x18 Sheet
    print("[3/5] Planning print job imposition on 12.0 x 18.0 inch sheet...")
    card_w = 3.5
    card_h = 2.0
    sheet_w = 12.0
    sheet_h = 18.0
    margin = 0.5
    gutter = 0.125
    bleed = 0.0

    plan = plan_print_job(
        file_path=str(artwork_file),
        finished_width_inches=card_w,
        finished_height_inches=card_h,
        sheet_width_inches=sheet_w,
        sheet_height_inches=sheet_h,
        copies=24,  # Try full sheet capacity
        margin_inches=margin,
        gutter_inches=gutter,
        bleed_inches=bleed,
        minimum_dpi=250.0,
        rotation_policy="best_fit",
    )

    layout = plan["layout"]
    print(f"      Ready for execution: {plan['ready_for_execution']}")
    print(f"      Effective DPI: {plan['effective_dpi']['minimum']} DPI (High Print Quality)")
    print(f"      Strategy: {layout['layout_strategy']}")
    print(f"      Capacity: {layout['capacity']} copies/sheet ({layout['columns']} cols x {layout['rows']} rows)")
    print(f"      Paper Waste: {layout['waste_percent']}%")
    print(f"      Placements calculated: {len(plan['placements'])}")

    # Step 3: Prepare Print Job in CorelDRAW X7 Live
    print("[4/5] Executing prepare_print_job live in CorelDRAW X7...")
    bridge.connect()
    t0 = time.perf_counter()
    job_result = bridge.prepare_print_job(
        file_path=str(artwork_file),
        finished_width_inches=card_w,
        finished_height_inches=card_h,
        sheet_width_inches=sheet_w,
        sheet_height_inches=sheet_h,
        copies=24,
        margin_inches=margin,
        gutter_inches=gutter,
        bleed_inches=bleed,
        minimum_dpi=250.0,
        object_name_prefix="CoffeeCard",
        rotation_policy="best_fit",
    )
    dur = (time.perf_counter() - t0) * 1000
    print(f"      Created and imposed {job_result['created_count']} copies in {dur:.1f}ms")
    print(f"      Post-execution verification: {job_result['post_execution_verification']}")
    assert not job_result["discrepancies"], f"Discrepancies found: {job_result['discrepancies']}"

    # Step 4: Persist and Export
    doc = bridge.target_doc
    try:
        print("[5/5] Saving production CDR and exporting PDF...")
        bridge.save_document(str(cdr_output))
        bridge.export_pdf(str(pdf_output))

        print("\n" + "=" * 60)
        print("PRINT JOB IMPOSITION SUCCESSFULLY GENERATED & VERIFIED!")
        print(f"Sheet Size:    {sheet_w} x {sheet_h} inches")
        print(f"Artwork Size:  {card_w} x {card_h} inches (300 DPI)")
        print(f"Imposed Count: {job_result['created_count']} copies on 1 sheet (3 x 8 grid)")
        print(f"CDR File:      {cdr_output} ({cdr_output.stat().st_size:,} bytes)")
        print(f"PDF File:      {pdf_output} ({pdf_output.stat().st_size:,} bytes)")
        print("=" * 60)

        return {
            "status": "SUCCESS",
            "plan": plan,
            "job_result": job_result,
            "cdr_path": str(cdr_output),
            "pdf_path": str(pdf_output),
        }
    finally:
        if doc is not None:
            try:
                doc.Close()
                print("Document closed cleanly.")
            except Exception as e:
                print(f"Close warning: {e}")
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    run_print_job_live_test()
