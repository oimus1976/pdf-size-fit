"""Experimental PDF size-fit diagnostics and route PoCs."""

from .diagnose import Diagnosis, Route, diagnose_pdf
from .image_fit import ImageFitAttempt, ImageFitResult, ImageFitStatus, fit_image_heavy_pdf
from .monochrome_fit import (
    MonochromeFitResult,
    MonochromeFitStatus,
    fit_monochrome_vector_pdf,
)

__all__ = [
    "Diagnosis",
    "Route",
    "diagnose_pdf",
    "ImageFitAttempt",
    "ImageFitResult",
    "ImageFitStatus",
    "fit_image_heavy_pdf",
    "MonochromeFitResult",
    "MonochromeFitStatus",
    "fit_monochrome_vector_pdf",
]
