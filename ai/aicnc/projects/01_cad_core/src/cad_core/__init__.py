"""Shared STEP/OCCT geometry services for AI-CNC."""

from .core import CAD_CORE_SCHEMA, CAD_CORE_VERSION, CadDocument
from .edge_projection import (
    EDGE_PROJECTION_SCHEMA,
    build_edge_projection,
    validate_edge_projection,
)
from .errors import CadCoreError, FaceAlignmentError, StepImportError
from .postprocess_context import build_postprocess_context

__all__ = [
    "CAD_CORE_SCHEMA",
    "CAD_CORE_VERSION",
    "CadCoreError",
    "CadDocument",
    "EDGE_PROJECTION_SCHEMA",
    "FaceAlignmentError",
    "StepImportError",
    "build_edge_projection",
    "build_postprocess_context",
    "validate_edge_projection",
]
