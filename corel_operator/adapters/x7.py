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
    CDR_FALSE = 0
    CDR_TRUE = -1

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
        "application.status": CapabilitySupport(
            True,
            "implemented_unverified",
            "X7 version and document-status properties are documented and type-library confirmed.",
            ("Application.Version", "Application.ActiveDocument"),
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
            "Application.ActiveDocument is available; bridge confirmation remains mandatory.",
            ("Application.ActiveDocument",),
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
