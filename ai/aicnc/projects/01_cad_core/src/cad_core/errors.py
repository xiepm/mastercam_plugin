"""Typed failures at the CAD Core boundary."""


class CadCoreError(RuntimeError):
    """Base class for deterministic CAD Core failures."""


class StepImportError(CadCoreError):
    """Raised when a STEP file cannot enter the supported B-Rep contract."""


class FaceAlignmentError(CadCoreError):
    """Raised when P01 Face records do not align with a model graph."""
