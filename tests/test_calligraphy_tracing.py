from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from corel_operator.calligraphy_tracing import (
    binary_mask,
    boundary_loops,
    connected_components,
    extract_warm_calligraphy_mask,
    filtered_mask,
    mask_metrics,
    rasterize_pen_commands,
    rasterize_traces,
    signed_area,
    simplify_closed_loop,
    trace_components,
    trace_summary,
)


class CalligraphyTracingTests(unittest.TestCase):
    def _fixture(self) -> Image.Image:
        image = Image.new("L", (80, 60), 0)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 54, 48), radius=9, fill=255)
        draw.ellipse((22, 18, 40, 36), fill=0)
        draw.ellipse((63, 11, 70, 18), fill=255)
        image.putpixel((2, 2), 255)
        return image

    def test_binary_mask_validates_threshold(self) -> None:
        image = Image.new("L", (2, 1))
        image.putdata([127, 128])
        self.assertEqual(list(binary_mask(image).tobytes()), [0, 255])
        with self.assertRaises(ValueError):
            binary_mask(image, -1)

    def test_warm_mask_extraction_is_bounded_and_closes_small_gap(self) -> None:
        image = Image.new("RGB", (20, 12), (60, 50, 45))
        draw = ImageDraw.Draw(image)
        draw.rectangle((3, 3, 7, 8), fill=(170, 120, 70))
        draw.rectangle((9, 3, 13, 8), fill=(170, 120, 70))
        image.putpixel((17, 5), (230, 225, 220))
        raw, clean = extract_warm_calligraphy_mask(
            image,
            region=(2, 2, 19, 10),
            closing_size=3,
        )
        self.assertEqual(len(connected_components(raw)), 3)
        self.assertEqual(len(connected_components(clean)), 2)
        self.assertEqual(raw.getpixel((0, 0)), 0)
        with self.assertRaises(ValueError):
            extract_warm_calligraphy_mask(image, region=(-1, 0, 10, 10))

    def test_pen_commands_rasterize_closed_analysis_geometry(self) -> None:
        mask = rasterize_pen_commands(
            (20, 20),
            [
                ("M", 2, 2),
                ("L", 17, 2),
                ("C", 17, 7, 17, 12, 17, 17),
                ("L", 2, 17),
                ("Z",),
            ],
        )
        self.assertEqual(mask.getbbox(), (2, 2, 18, 18))
        self.assertGreater(mask.histogram()[255], 200)
        with self.assertRaises(ValueError):
            rasterize_pen_commands((10, 10), [("M", 1, 1), ("L", 2, 2)])

    def test_components_are_filtered_and_ordered_by_area(self) -> None:
        components = connected_components(self._fixture(), minimum_area=4)
        self.assertEqual(len(components), 2)
        self.assertEqual([item.label for item in components], [1, 2])
        self.assertGreater(components[0].area, components[1].area)
        self.assertEqual(components[1].bbox, (63, 11, 71, 19))
        self.assertEqual(
            filtered_mask(self._fixture().size, components).getbbox(),
            (8, 8, 71, 49),
        )

    def test_boundary_loops_preserve_outer_and_counterform_orientation(self) -> None:
        component = connected_components(self._fixture(), minimum_area=100)[0]
        loops = boundary_loops(component)
        self.assertEqual(len(loops), 2)
        self.assertGreater(signed_area(loops[0]), 0)
        self.assertLess(signed_area(loops[1]), 0)

    def test_simplification_reduces_nodes_without_flipping_ring(self) -> None:
        component = connected_components(self._fixture(), minimum_area=100)[0]
        outer = boundary_loops(component)[0]
        simplified = simplify_closed_loop(outer, 1.0)
        self.assertLess(len(simplified), len(outer))
        self.assertGreater(signed_area(simplified), 0)

    def test_traces_are_named_and_rasterize_close_to_mask(self) -> None:
        fixture = self._fixture()
        components = connected_components(fixture, minimum_area=4)
        traces = trace_components(
            components,
            simplify_tolerance=0.5,
            principal_area=100,
        )
        self.assertEqual(traces[0].role, "main_connected_composition")
        self.assertEqual(traces[1].role, "diacritic_or_detached_mark")
        rendered = rasterize_traces(fixture.size, traces)
        expected = filtered_mask(fixture.size, components)
        metrics = mask_metrics(expected, rendered)
        self.assertGreater(metrics["iou"], 0.90)
        self.assertGreater(metrics["f1"], 0.95)
        summary = trace_summary(traces)
        self.assertEqual(summary["component_count"], 2)
        self.assertEqual(summary["counterform_holes"], 1)

    def test_mask_metrics_rejects_dimension_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            mask_metrics(Image.new("1", (2, 2)), Image.new("1", (3, 2)))


if __name__ == "__main__":
    unittest.main()
