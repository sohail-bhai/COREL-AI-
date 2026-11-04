"""CorelDRAW X7 (major version 17) compatibility profile."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ..errors import CorelBridgeError, ErrorCode
from ..version import CAPABILITY_PROFILE_ID


@dataclass(frozen=True)
class CapabilitySupport:
    available: bool
    status: str
    reason: str
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence"] = list(self.evidence)
        return value


class CorelX7Adapter:
    """Central X7 identity, constants, version checks, and capability status."""

    PROFILE_ID = CAPABILITY_PROFILE_ID
    PRODUCT = "CorelDRAW Graphics Suite X7"
    PRODUCT_MAJOR = 17
    VERIFIED_BUILDS = ("17.0.0.491",)
    API_REFERENCE_ROOT = "https://community.coreldraw.com/sdk/api/draw/17/"

    EXPLICIT_PROG_ID = "CorelDRAW.Application.17"
    GENERIC_PROG_ID = "CorelDRAW.Application"
    PROG_IDS = (EXPLICIT_PROG_ID, GENERIC_PROG_ID)
    CONNECTION_CANDIDATES = (
        ("GetActiveObject", EXPLICIT_PROG_ID),
        ("GetActiveObject", GENERIC_PROG_ID),
        ("Dispatch", EXPLICIT_PROG_ID),
        ("Dispatch", GENERIC_PROG_ID),
    )

    # Values confirmed through the installed CorelDRAW 17 type library.
    CDR_INCH = 1
    CDR_BOTTOM_LEFT = 5
    CDR_FILTER_AUTO_SENSE = 0
    CDR_FILTER_CDR = 1795
    CDR_CURRENT_VERSION = 0
    CDR_ALL_PAGES = 0
    CDR_LANGUAGE_NONE = 0
    CDR_CHARSET_ANSI = 0
    CDR_CHARSET_MIXED = -1
    CDR_FALSE = 0
    CDR_TRUE = -1
    CDR_GROUP_SHAPE = 7
    CDR_TEXT_SHAPE = 6
    CDR_CURVE_SHAPE = 3
    VECTOR_PRIMITIVE_TYPES = (1,2,3,4)
    NODE_TYPE_CODES = {'cusp':0,'smooth':1,'symmetrical':2}
    SEGMENT_TYPE_CODES = {'line':0,'cubic':1}
    TRANSPARENCY_TYPE_NAMES = {0:'none',1:'uniform',2:'fountain',3:'pattern',4:'texture'}
    TRANSPARENCY_APPLIED_TO = {'fill':0,'outline':1,'both':2}
    CDR_MERGE_NORMAL = 0
    FLIP_AXES = {"horizontal": 1, "vertical": 2, "both": 3}

    CDR_ALIGN_DISTRIBUTE_H_NONE = 0
    CDR_ALIGN_DISTRIBUTE_H_ALIGN_RIGHT = 1
    CDR_ALIGN_DISTRIBUTE_H_ALIGN_LEFT = 2
    CDR_ALIGN_DISTRIBUTE_H_ALIGN_CENTER = 3

    CDR_ALIGN_DISTRIBUTE_V_NONE = 0
    CDR_ALIGN_DISTRIBUTE_V_ALIGN_TOP = 1
    CDR_ALIGN_DISTRIBUTE_V_ALIGN_BOTTOM = 2
    CDR_ALIGN_DISTRIBUTE_V_ALIGN_CENTER = 3

    CDR_ALIGN_SHAPES_TO_LAST_SELECTED = 0
    CDR_ALIGN_SHAPES_TO_EDGE_OF_PAGE = 1
    CDR_ALIGN_SHAPES_TO_CENTER_OF_PAGE = 2

    CDR_ALIGN_LEFT = 1
    CDR_ALIGN_RIGHT = 2
    CDR_ALIGN_H_CENTER = 3
    CDR_ALIGN_TOP = 4
    CDR_ALIGN_BOTTOM = 8
    CDR_ALIGN_V_CENTER = 12

    GRADIENT_TYPE_CODES = {"linear": 1, "radial": 2, "conical": 3, "square": 4}
    CDR_DIRECT_FOUNTAIN_BLEND = 0
    CDR_CUSTOM_FOUNTAIN_BLEND = 3
    CDR_FOUNTAIN_SPREAD_PAD = 0
    CDR_CONTOUR_EFFECT = 6
    CDR_CONTOUR_GROUP_SHAPE = 13
    CDR_CONTOUR_BUTT_CAP = 0
    CONTOUR_DIRECTION_CODES = {"inside": 0, "outside": 1}
    CONTOUR_CORNER_CODES = {"bevel": 0, "offset_bevel": 1, "round": 2,
                            "mitered_bevel": 3, "mitered_offset_bevel": 4, "mitered_round": 5}

    FILL_TYPE_NAMES = {
        0: "none",
        1: "uniform",
        2: "fountain",
        3: "postscript",
        8: "texture",
        9: "pattern",
        10: "hatch",
    }
    OUTLINE_TYPE_NAMES = {
        0: "none",
        1: "outline",
        2: "enhanced",
    }
    COLOR_TYPE_NAMES = {
        1: "pantone",
        2: "cmyk",
        4: "cmy",
        5: "rgb",
        6: "hsb",
        7: "hls",
        8: "black_and_white",
        9: "gray",
        11: "yiq",
        12: "lab",
        14: "pantone_hex",
        20: "registration",
        22: "user_ink",
        25: "spot",
        26: "multi_channel",
        99: "mixed",
    }

    UNIT_NAMES = {
        0: "tenth-micron",
        1: "inch",
        2: "foot",
        3: "millimeter",
        4: "centimeter",
        5: "pixel",
        6: "mile",
        7: "meter",
        8: "kilometer",
        9: "didot",
        10: "agate",
        11: "yard",
        12: "pica",
        13: "cicero",
        14: "point",
        15: "Q",
        16: "H",
    }

    _CURRENT_CAPABILITIES = {
        "images.document_raster_preflight": CapabilitySupport(True, "implemented_unverified", "Two bounded native graph scans cover printable page/applied master layers, groups and PowerClips with DPI/local-link presence evidence and preserved context; partial, stale, effect/EPS/uncertain coordinate coverage cannot establish a pass.",
            ("Bitmap.LinkFileName", "Bitmap.OPILinked", "Bitmap.IsEPS", "Shape.PowerClipParent", "Document.SelectionRange", "Page.AllLayers")),
        "images.raster_asset_inspection": CapabilitySupport(True, "implemented_unverified", "Bounded local raster snapshots, EXIF-normalized decoded pixel/source hashes, dimensions, alpha and opaque ICC/DPI metadata; no native dependency or color approval.",
            ()),
        "images.raster_preparation": CapabilitySupport(True, "implemented_unverified", "Fingerprint-guarded PNG/TIFF derivatives with crop/quarter rotation/flips/fitting and verified pixels, metadata and unchanged source bytes; Corel import and visual review remain deferred.",
            ()),
        "images.bitmap_inspection": CapabilitySupport(True, "implemented_unverified", "Native pixel/mode/link/crop metadata plus placed affine pixel-grid resolution, including minimum directional DPI; unclear/effect/clipping geometry remains indeterminate and native semantics require deferred verification.",
            ("Shape.Bitmap", "Bitmap.SizeWidth", "Bitmap.SizeHeight", "Bitmap.BoundingBoxPath", "Shape.GetMatrix")),
        "document.organization_inspection": CapabilitySupport(True, "implemented_unverified", "Bounded page/local/master layer structure, active context, root identities and current-session fingerprints; native verification remains deferred.",
            ("Document.Pages", "Document.MasterPage", "Page.Layers", "Page.AllLayers")),
        "document.page_organization": CapabilitySupport(True, "implemented_unverified", "Fingerprint-guarded page activation/rename and source-preserving appended empty pages; existing-page resize/reorder/deletion remain deferred.",
            ("Document.AddPages", "Page.Activate", "Page.Name", "Page.SetSize")),
        "document.layer_organization": CapabilitySupport(True, "implemented_unverified", "Fingerprint-guarded ordinary local layer creation/name/visible/editable/printable changes; master/special edits and cross-layer moves remain deferred.",
            ("Page.CreateLayer", "Layer.Name", "Layer.Visible", "Layer.Editable", "Layer.Printable")),
        "vectors.contour_offsets": CapabilitySupport(True, "implemented_unverified", "Copied closed vectors produce separated editable contour derivatives with native distance/corner controls, complete owned-tree cleanup and measured source preservation; exact arbitrary-curve/cutting behavior remains deferred.",
            ("Shape.CreateContour", "Shape.Effects", "Effect.Contour", "Effect.Separate", "EffectContour.ContourGroup")),
        "appearance.gradient_inspection": CapabilitySupport(True, "implemented_unverified", "Bounded native stop/parameter/coordinate metadata and current-session fingerprints; missing getters remain explicit.",
            ("Fill.Fountain", "FountainFill.Colors", "FountainColors.Item", "FountainColor.Position", "FountainColor.Color")),
        "appearance.gradient_fill": CapabilitySupport(True, "implemented_unverified", "Opaque direct 2-32-stop RGB/CMYK gradients reconcile parameters, colors and measured geometry/other channels; revisions require a fingerprint and partial writes quarantine.",
            ("Fill.ApplyFountainFill", "FountainColors.Add", "FountainColor.MidPoint", "FountainColor.BlendType", "FountainFill.MakeOpaque")),
        "appearance.powerclip_inspection": CapabilitySupport(True,"implemented_unverified","Bounded native group/clip trees, measured geometry/body metadata and source-bound fingerprints; clipped children require extraction for ordinary editing references.",
            ("Shape.PowerClip","PowerClip.Parent","PowerClip.Shapes","PowerClip.ContentsLocked")),
        "appearance.powerclip_create": CapabilitySupport(True,"implemented_unverified","Independent frame/content copies, grouped payloads and contain/cover fitting reconcile complete measured trees and preserve sources; native/visual gate pending.",
            ("Shape.Duplicate","Shape.AddToPowerClip","ShapeRange.Group","PowerClip.ContentsLocked")),
        "appearance.powerclip_extract": CapabilitySupport(True,"implemented_unverified","Copied clip extraction reconciles native identities/tree geometry and returns independent root editing references with owned-output cleanup.",
            ("Shape.Duplicate","PowerClip.ExtractShapes","PowerClip.Shapes","Shape.Delete")),
        "appearance.transparency_inspection": CapabilitySupport(True,"implemented_unverified","Bounded transparency type/uniform/channel/merge metadata with explicit unavailable state; rendered appearance remains unverified.",
            ("Shape.Transparency","Transparency.Type","Transparency.Uniform","Transparency.AppliedTo","Transparency.MergeMode")),
        "appearance.uniform_transparency": CapabilitySupport(True,"implemented_unverified","Normal-mode uniform fill/outline/both transparency and removal verify native state and measured/base-appearance preservation.",
            ("Transparency.ApplyUniformTransparency","Transparency.ApplyNoTransparency","Transparency.AppliedTo","Transparency.MergeMode")),
        "appearance.process_color": CapabilitySupport(True,"implemented_unverified","Native RGB/CMYK process fill/ordinary-outline assignment verifies complete components and measured geometry/other-channel preservation; no ICC/spot proof.",
            ("Application.CreateRGBColor","Application.CreateCMYKColor","Fill.ApplyUniformFill","Outline.Color")),
        "vector.revise_topology": CapabilitySupport(True,"implemented_unverified","Source-preserving parameter subdivision and explicit nonadjacent node reconnection with complete native geometry/appearance readback.",
            ("Curve.CopyAssign","Shape.Duplicate","Node.Type")),
        "vector.create_path": CapabilitySupport(True,"implemented_unverified","Bounded editable line/cubic subpaths with complete native geometry readback; live gate pending.",
            ("Application.CreateCurve","Curve.CreateSubPath","SubPath.AppendLineSegment","SubPath.AppendCurveSegment2","Layer.CreateCurve")),
        "vector.inspect_geometry": CapabilitySupport(True,"implemented_unverified","Native node/handle topology and read-only primitive display curves are fingerprinted for exact targeting.",
            ("Shape.Curve","Shape.DisplayCurve","Curve.SubPaths","Curve.Nodes","Curve.Segments")),
        "vector.edit_geometry": CapabilitySupport(True,"implemented_unverified","Complete node/handle preflight, explicit cusp conversion, whole-curve readback and partial-failure quarantine.",
            ("Node.SetPosition","Node.Type","Segment.SetStartingControlPointPosition","Segment.SetEndingControlPointPosition")),
        "vector.boolean": CapabilitySupport(True,"implemented_unverified","Weld/trim/intersect operate on owned copies and verify measured inputs and membership; live semantics pending.",
            ("Shape.Duplicate","Shape.Weld","Shape.Trim","Shape.Intersect")),
        "vector.combine": CapabilitySupport(True,"implemented_unverified","Independent compound outputs preserve and reconcile input subpath geometry after owned conversion/copy.",
            ("Application.CreateShapeRange","ShapeRange.Combine","Shape.ConvertToCurves")),
        "vector.break_apart": CapabilitySupport(True,"implemented_unverified","Owned copied subpaths are matched to source geometry and counted before output acceptance.",
            ("Shape.BreakApartEx","ShapeRange.Item","ShapeRange.Count")),
        "pdf.inspect": CapabilitySupport(
            True,"implemented_unverified","Bounded local PDF page boxes/counts and font-program presence checks; no renderer or ICC/PDF-X proof.",(),
        ),
        "pdf.controlled_export": CapabilitySupport(
            True,"implemented_unverified","Explicit whole-document zero-bleed controls, verified settings restoration, parsed artifact checks and exclusive publication. Native/manual gates deferred.",
            ("Document.PDFSettings","Document.PublishToPDF"),
        ),
        "template.inspect": CapabilitySupport(
            True,"implemented_unverified","Bounded grouped text-template snapshots bind measured structure/text/basic appearance to a signed source reference.",
            ("Shape.Shapes","Shape.GetMatrix","Text.Story"),
        ),
        "template.csv_data": CapabilitySupport(
            True,"implemented_unverified","Local literal UTF-8 CSV parsing enforces complete bounded rows and unique headers without a native call.",(),
        ),
        "template.batch_plan": CapabilitySupport(
            True,"implemented_unverified","Data, duplicates, named fields, regions and multiple output sheets form a complete fingerprinted local plan.",(),
        ),
        "template.batch_execute": CapabilitySupport(
            True,"implemented_unverified","Independent output documents/copies are rechecked after all edits; owned discard and source observations gate rollback. Native behavior awaits the consolidated campaign.",
            ("Application.CreateDocument","Shape.Copy","Layer.Paste","Shape.Duplicate","Document.AddPagesEx","Document.Dirty","Document.Close"),
        ),
        "object.transform_inspect": CapabilitySupport(
            True, "implemented_unverified",
            "Finite X7 matrix/rotation/bounds readback is implemented; native matrix conventions await the consolidated gate.",
            ("Shape.GetMatrix", "Shape.RotationAngle", "Shape.ZOrder"),
        ),
        "object.rotate": CapabilitySupport(
            True, "implemented_unverified",
            "Explicit-pivot relative/absolute rotation uses X7 RotateEx with signed targeting and actual angle/bounds readback.",
            ("Shape.RotateEx", "Shape.GetMatrix", "Shape.RotationAngle"),
        ),
        "object.flip": CapabilitySupport(
            True, "implemented_unverified",
            "X7 mirror axes are confirmed; actual matrix parity is checked but native rendering remains unverified.",
            ("Shape.Flip", "Shape.GetMatrix"),
        ),
        "object.order": CapabilitySupport(
            True, "implemented_unverified",
            "Native sibling relations and membership verify four stacking edits; nested X7 behavior awaits live testing.",
            ("Shape.OrderToFront", "Shape.OrderToBack", "Shape.OrderIsInFrontOf", "Shape.ParentGroup"),
        ),
        "object.distribute": CapabilitySupport(
            True, "implemented_unverified",
            "Measured equal-gap/equal-center/explicit-gap plans use exact references and verify every resulting bound; partial failures require recovery.",
            ("Shape.SetPosition", "Shape.GetMatrix", "Document.Unit", "Document.ReferencePoint"),
        ),
        "text.paragraph_create": CapabilitySupport(
            True, "implemented_unverified",
            "X7 paragraph creation signature is confirmed; native text/glyph/overflow behavior awaits the consolidated live gate.",
            ("Layer.CreateParagraphText", "Text.Type", "Text.Overflow"),
        ),
        "text.style_edit": CapabilitySupport(
            True, "implemented_unverified",
            "Whole-story editing with signed targeting, font preflight and formatting readback passes fake-COM tests; linked/fitted text is refused.",
            ("Text.Story", "Text.Frames", "TextRange.Font", "TextRange.Size", "TextRange.Alignment"),
        ),
        "text.font_catalog": CapabilitySupport(
            True, "implemented_unverified",
            "Bounded X7 font catalog inspection is type-library confirmed; catalog membership does not establish glyph coverage.",
            ("Application.FontList", "FontList.Count", "FontList.Item"),
        ),
        "application.status": CapabilitySupport(
            True,
            "implemented_unverified",
            "X7 version and document-status properties are documented and type-library confirmed.",
            ("Application.Version", "Application.ActiveDocument"),
        ),
        "document.list_open": CapabilitySupport(
            True,
            "implemented_unverified",
            "Application.Documents is available; process-local identity and closure behavior need live tests.",
            ("Application.Documents", "Document.Name", "Document.FullFileName"),
        ),
        "document.inspect": CapabilitySupport(
            True,
            "implemented_unverified",
            "Document state members are confirmed; bounded open-document identity guards detect stale bindings in fake-COM tests.",
            ("Application.Documents", "Document.Name", "Document.Dirty", "Document.Pages", "Document.ActivePage"),
        ),
        "page.list": CapabilitySupport(
            True,
            "implemented_unverified",
            "Page collection and size members are available; multi-page behavior needs live tests.",
            ("Document.Pages", "Page.Index", "Page.SizeWidth", "Page.SizeHeight"),
        ),
        "page.bounds": CapabilitySupport(
            True,
            "implemented_unverified",
            "Page-local bounds can be derived from size; facing-page semantics need live tests.",
            ("Page.SizeWidth", "Page.SizeHeight"),
        ),
        "layer.list": CapabilitySupport(
            True,
            "implemented_unverified",
            "Page layer collections and basic layer state members are type-library confirmed.",
            ("Page.Layers", "Page.AllLayers", "Layer.Name", "Layer.Shapes"),
        ),
        "object.inspect": CapabilitySupport(
            True,
            "implemented_unverified",
            "Shape identity, geometry, text, fill, and outline members are available; nesting remains limited.",
            ("Shape.Name", "Shape.StaticID", "Shape.Fill", "Shape.Outline"),
        ),
        "object.find": CapabilitySupport(
            True,
            "implemented_unverified",
            "Bounded page/layer/group enumeration uses X7-confirmed members; live search behavior remains unverified.",
            ("Page.AllLayers", "Layer.Shapes", "Shape.Shapes", "Shape.StaticID", "TextRange.Text"),
        ),
        "object.bounds": CapabilitySupport(
            True,
            "implemented_unverified",
            "Focused bounds inspection restores units/reference point; ruler-origin semantics need live verification.",
            ("Shape.PositionX", "Shape.PositionY", "Shape.SizeWidth", "Shape.SizeHeight"),
        ),
        "text.inspect": CapabilitySupport(
            True,
            "implemented_unverified",
            "Bounded story and aggregate formatting inspection uses confirmed X7 properties; text runs remain unsupported.",
            ("Text.Story", "TextRange.Text", "TextRange.Font", "TextRange.Size", "TextRange.Bold", "TextRange.Italic"),
        ),
        "fill.inspect": CapabilitySupport(
            True,
            "implemented_unverified",
            "Fill type and native uniform color inspection preserve color models; complex fill details remain unsupported.",
            ("Fill.Type", "Fill.UniformColor", "Color.Type"),
        ),
        "document.create": CapabilitySupport(
            True,
            "implemented_unverified",
            "Application.CreateDocument and Page.SetSize are available in X7.",
            ("Application.CreateDocument", "Page.SetSize"),
        ),
        "document.bind_active": CapabilitySupport(
            True,
            "implemented_unverified",
            "Active-document binding requires confirmation and live collection membership; runtime lifetime behavior remains unverified.",
            ("Application.ActiveDocument", "Application.Documents"),
        ),
        "text.create_artistic": CapabilitySupport(
            True,
            "implemented_unverified",
            "Layer.CreateArtisticText is documented and type-library confirmed.",
            ("Layer.CreateArtisticText",),
        ),
        "shape.create_rectangle": CapabilitySupport(
            True,
            "implemented_unverified",
            "Layer.CreateRectangle2 is documented and type-library confirmed.",
            ("Layer.CreateRectangle2",),
        ),
        "shape.create_ellipse": CapabilitySupport(
            True,
            "implemented_unverified",
            "Layer.CreateEllipse2 is documented and type-library confirmed.",
            ("Layer.CreateEllipse2",),
        ),
        "object.list": CapabilitySupport(
            True,
            "implemented_unverified",
            "Page.Shapes and required basic Shape properties are available.",
            ("Page.Shapes", "Shape.Name", "Shape.Type"),
        ),
        "fill.uniform_rgb": CapabilitySupport(
            True,
            "implemented_unverified",
            "CreateRGBColor and ApplyUniformFill are available; readback is pending.",
            ("Application.CreateRGBColor", "Fill.ApplyUniformFill"),
        ),
        "outline.set": CapabilitySupport(
            True,
            "implemented_unverified",
            "Outline color/width members exist, but width units still need a live test.",
            ("Outline.Color", "Outline.Width", "Outline.SetNoOutline"),
        ),
        "outline.width_points": CapabilitySupport(
            False,
            "research_required",
            "Current evidence does not establish that Outline.Width uses points at the MCP boundary.",
            ("Outline.Width",),
        ),
        "shape.set_position": CapabilitySupport(
            True,
            "implemented_unverified",
            "Shape.SetPosition is available; drawing-origin behavior needs verification.",
            ("Shape.SetPosition", "Document.ReferencePoint"),
        ),
        "shape.set_size": CapabilitySupport(
            True,
            "implemented_unverified",
            "Shape size properties are available; resize-anchor behavior needs verification.",
            ("Shape.SizeWidth", "Shape.SizeHeight"),
        ),
        "text.replace_story": CapabilitySupport(
            True,
            "implemented_unverified",
            "Text.Story and TextRange.Text are available; formatting preservation is pending.",
            ("Text.Story", "TextRange.Text"),
        ),
        "shape.rename": CapabilitySupport(
            True,
            "implemented_unverified",
            "Shape.Name is writable; persistent identity remains separate research.",
            ("Shape.Name",),
        ),
        "shape.duplicate": CapabilitySupport(
            True,
            "implemented_unverified",
            "Shape.Duplicate is documented and type-library confirmed.",
            ("Shape.Duplicate",),
        ),
        "artwork.import": CapabilitySupport(
            True,
            "implemented_unverified",
            "Layer.Import exists; individual file filters remain unverified.",
            ("Layer.Import",),
        ),
        "document.save_cdr": CapabilitySupport(
            True,
            "implemented_unverified",
            "Document.SaveAs and X7 save-option constants are available.",
            ("Document.SaveAs", "StructSaveAsOptions.Filter"),
        ),
        "document.publish_pdf": CapabilitySupport(
            True,
            "implemented_unverified",
            "Document.PublishToPDF exists; effective PDF settings remain unverified.",
            ("Document.PublishToPDF",),
        ),
        "shape.align_objects": CapabilitySupport(
            True,
            "implemented_unverified",
            "ShapeRange.AlignAndDistribute aligns multiple shapes to reference target.",
            ("Application.CreateShapeRange", "ShapeRange.AlignAndDistribute"),
        ),
        "shape.align_to_page": CapabilitySupport(
            True,
            "implemented_unverified",
            "ShapeRange.AlignAndDistribute and AlignRangeToPage align shapes to page edges or center.",
            ("Application.CreateShapeRange", "ShapeRange.AlignAndDistribute", "ShapeRange.AlignRangeToPage", "ShapeRange.AlignRangeToPageCenter"),
        ),
        "shape.group": CapabilitySupport(
            True,
            "implemented_unverified",
            "ShapeRange.Group combines shapes into a single group shape.",
            ("Application.CreateShapeRange", "ShapeRange.Group"),
        ),
        "shape.ungroup": CapabilitySupport(
            True,
            "implemented_unverified",
            "Shape.Ungroup and UngroupAll release shapes from groups.",
            ("Shape.Ungroup", "Shape.UngroupAll"),
        ),
    }

    @classmethod
    def application_info(cls, app: Any, prog_id: str | None = None) -> dict[str, Any]:
        version_string = cls._safe_attr(app, "Version")
        major = cls._coerce_int(cls._safe_attr(app, "VersionMajor"))
        minor = cls._coerce_int(cls._safe_attr(app, "VersionMinor"))
        build = cls._coerce_int(cls._safe_attr(app, "VersionBuild"))
        if major is None and isinstance(version_string, str):
            match = re.search(r"(?:Version\s+)?(\d+)(?:\.(\d+))?", version_string)
            if match:
                major = int(match.group(1))
                if minor is None and match.group(2) is not None:
                    minor = int(match.group(2))
        return {
            "version": version_string,
            "version_major": major,
            "version_minor": minor,
            "version_build": build,
            "prog_id": prog_id,
        }

    @classmethod
    def validate_application(cls, app: Any, prog_id: str | None = None) -> dict[str, Any]:
        info = cls.application_info(app, prog_id)
        major = info["version_major"]
        if major is None:
            raise CorelBridgeError(
                "Could not determine the connected CorelDRAW major version.",
                ErrorCode.UNSUPPORTED_IN_PROFILE,
                {"expected_major": cls.PRODUCT_MAJOR, "prog_id": prog_id},
            )
        if major != cls.PRODUCT_MAJOR:
            raise CorelBridgeError(
                f"Connected CorelDRAW major version {major} does not match required X7 major version {cls.PRODUCT_MAJOR}.",
                ErrorCode.UNSUPPORTED_IN_PROFILE,
                {
                    "expected_major": cls.PRODUCT_MAJOR,
                    "detected_major": major,
                    "prog_id": prog_id,
                },
            )
        return info

    @classmethod
    def supports(cls, capability: str, require_verified: bool = False) -> bool:
        support = cls._CURRENT_CAPABILITIES.get(capability)
        if support is None or not support.available:
            return False
        if require_verified:
            return support.status == "verified"
        return True

    @classmethod
    def capability_details(cls, capability: str) -> dict[str, Any]:
        support = cls._CURRENT_CAPABILITIES.get(capability)
        if support is None:
            return {
                "capability": capability,
                "available": False,
                "status": "unsupported",
                "reason": "Capability is not present in the approved X7 profile.",
                "evidence": [],
            }
        return {"capability": capability, **support.as_dict()}

    @classmethod
    def capabilities(cls) -> dict[str, dict[str, Any]]:
        return {
            name: cls.capability_details(name)
            for name in sorted(cls._CURRENT_CAPABILITIES)
        }

    @classmethod
    def profile_summary(cls) -> dict[str, Any]:
        available = sum(1 for support in cls._CURRENT_CAPABILITIES.values() if support.available)
        return {
            "profile_id": cls.PROFILE_ID,
            "product": cls.PRODUCT,
            "product_major": cls.PRODUCT_MAJOR,
            "verified_builds": list(cls.VERIFIED_BUILDS),
            "api_reference_root": cls.API_REFERENCE_ROOT,
            "preferred_prog_id": cls.EXPLICIT_PROG_ID,
            "fallback_prog_id": cls.GENERIC_PROG_ID,
            "capability_count": len(cls._CURRENT_CAPABILITIES),
            "available_capability_count": available,
            "verified_capability_count": sum(
                1 for support in cls._CURRENT_CAPABILITIES.values()
                if support.status == "verified"
            ),
        }

    @classmethod
    def unit_name(cls, value: int) -> str:
        return cls.UNIT_NAMES.get(value, "unknown")

    @staticmethod
    def _safe_attr(value: Any, name: str) -> Any:
        try:
            return getattr(value, name)
        except Exception:
            return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return None
