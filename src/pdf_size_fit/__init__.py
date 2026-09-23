"""Experimental PDF size-fit diagnostics and route PoCs."""

from .diagnose import Diagnosis, Route, diagnose_pdf
from .fit import FitResult, FitStatus, fit_pdf
from .image_fit import (
    ImageFitAttempt,
    ImageFitResult,
    ImageFitStatus,
    fit_image_heavy_pdf,
)
from .color_fit import (
    ColorFitResult,
    ColorFitStatus,
    fit_color_vector_pdf,
)
from .monochrome_fit import (
    MonochromeFitResult,
    MonochromeFitStatus,
    fit_monochrome_vector_pdf,
)
from .split import (
    SourceSnapshot,
    SplitEligibilityResult,
    SplitEligibilityStatus,
    SplitPart,
    SplitResult,
    SplitStatus,
    capture_source_snapshot,
    evaluate_split_eligibility,
    split_pdf,
)

__all__ = [
    "Diagnosis",
    "Route",
    "diagnose_pdf",
    "FitResult",
    "FitStatus",
    "fit_pdf",
    "ImageFitAttempt",
    "ImageFitResult",
    "ImageFitStatus",
    "fit_image_heavy_pdf",
    "ColorFitResult",
    "ColorFitStatus",
    "fit_color_vector_pdf",
    "MonochromeFitResult",
    "MonochromeFitStatus",
    "fit_monochrome_vector_pdf",
    "SourceSnapshot",
    "SplitEligibilityResult",
    "SplitEligibilityStatus",
    "SplitPart",
    "SplitResult",
    "SplitStatus",
    "capture_source_snapshot",
    "evaluate_split_eligibility",
    "split_pdf",
]
