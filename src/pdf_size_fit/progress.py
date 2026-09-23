from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ProgressPhase(str, Enum):
    IMAGE_OPTIMIZATION = "image_optimization"
    PAGE_OPTIMIZATION = "page_optimization"
    HIGH_QUALITY_SEARCH = "high_quality_search"


@dataclass(frozen=True)
class ProgressEvent:
    phase: ProgressPhase
    completed: int
    total: int


ProgressCallback = Callable[[ProgressEvent], None]


def report_progress(
    callback: ProgressCallback | None,
    event: ProgressEvent,
) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        # Progress is best-effort observational reporting.
        # Ordinary callback exceptions must not break compression execution or safety semantics.
        pass
