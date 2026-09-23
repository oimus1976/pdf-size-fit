from __future__ import annotations

import pytest

from pdf_size_fit.progress import ProgressEvent, ProgressPhase, report_progress


def test_progress_event_fields() -> None:
    event = ProgressEvent(
        phase=ProgressPhase.IMAGE_OPTIMIZATION,
        completed=2,
        total=9,
    )
    assert event.phase is ProgressPhase.IMAGE_OPTIMIZATION
    assert event.completed == 2
    assert event.total == 9


def test_report_progress_handles_none_callback() -> None:
    event = ProgressEvent(
        phase=ProgressPhase.PAGE_OPTIMIZATION,
        completed=1,
        total=5,
    )
    # Should not raise
    report_progress(None, event)


def test_report_progress_calls_callback() -> None:
    events: list[ProgressEvent] = []
    event = ProgressEvent(
        phase=ProgressPhase.PAGE_OPTIMIZATION,
        completed=1,
        total=5,
    )

    report_progress(events.append, event)

    assert events == [event]


def test_report_progress_suppresses_ordinary_exceptions() -> None:
    def buggy_callback(event: ProgressEvent) -> None:
        raise ValueError("buggy callback error")

    event = ProgressEvent(
        phase=ProgressPhase.IMAGE_OPTIMIZATION,
        completed=1,
        total=4,
    )

    # Should not raise exception
    report_progress(buggy_callback, event)


@pytest.mark.parametrize("exc_type", [KeyboardInterrupt, SystemExit])
def test_report_progress_reraises_process_control_exceptions(
    exc_type: type[BaseException],
) -> None:
    def process_exit_callback(event: ProgressEvent) -> None:
        raise exc_type()

    event = ProgressEvent(
        phase=ProgressPhase.IMAGE_OPTIMIZATION,
        completed=1,
        total=4,
    )

    with pytest.raises(exc_type):
        report_progress(process_exit_callback, event)
