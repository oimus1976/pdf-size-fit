from __future__ import annotations

import argparse
import json
import os
import queue
import threading
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Sequence

from .diagnose import Route
from .fit import FitResult, FitStatus, fit_pdf


SIMPLE_TARGET_BYTES = 10_000_000
SIMPLE_MIN_QUALITY = 70
SIMPLE_MIN_SCALE = 0.50
SIMPLE_ALLOW_TEXT_RASTERIZATION = False
ALREADY_BELOW_MESSAGE = "このPDFはすでに10MB以下です。変換は不要です。"
DEFAULT_TARGET_MB = "10"
DEFAULT_MIN_QUALITY = "70"
DEFAULT_MIN_SCALE_PERCENT = "100"


@dataclass(frozen=True)
class GuiRequest:
    input_path: Path
    output_path: Path
    target_bytes: int
    min_quality: int
    min_scale: float
    allow_small_searchable_text_rasterization: bool


@dataclass(frozen=True)
class ResultPresentation:
    category: str
    title: str
    summary: str
    details: str
    successful_output: Path | None = None


def suggest_output_path(input_path: str | Path) -> Path:
    """Return a same-directory, non-existing output path distinct from input."""
    source = Path(input_path)
    suffix = source.suffix if source.suffix.lower() == ".pdf" else ".pdf"
    stem = source.stem
    candidate = source.with_name(f"{stem}-fit{suffix}")
    number = 2
    while candidate.exists() or candidate.resolve() == source.resolve():
        candidate = source.with_name(f"{stem}-fit-{number}{suffix}")
        number += 1
    return candidate


def decimal_mb_to_bytes(value: str) -> int:
    """Convert decimal megabytes to an exact, positive integer byte count."""
    try:
        megabytes = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("目標サイズは数値で入力してください。") from None
    if not megabytes.is_finite() or megabytes <= 0:
        raise ValueError("目標サイズは 0 より大きい数値にしてください。")
    byte_value = megabytes * 1_000_000
    if byte_value != byte_value.to_integral_value():
        raise ValueError("目標サイズは 1 バイト単位に変換できる桁数で入力してください。")
    return int(byte_value)


def build_request(
    input_path: str,
    output_path: str,
    target_mb: str,
    min_quality: str,
    min_scale_percent: str,
    allow_small_searchable_text_rasterization: bool,
) -> GuiRequest:
    source = Path(input_path.strip())
    destination = Path(output_path.strip())
    if not input_path.strip():
        raise ValueError("入力 PDF を選択してください。")
    if not source.is_file():
        raise ValueError("入力 PDF が見つかりません。")
    if source.suffix.lower() != ".pdf":
        raise ValueError("入力ファイルには PDF を選択してください。")
    if not output_path.strip():
        raise ValueError("出力 PDF を指定してください。")
    if source.resolve() == destination.resolve():
        raise ValueError("出力先には入力 PDF と異なるパスを指定してください。")
    if destination.suffix.lower() != ".pdf":
        raise ValueError("出力ファイルには .pdf 拡張子を指定してください。")
    if not destination.parent.is_dir():
        raise ValueError("出力先のフォルダーが見つかりません。")
    if destination.exists():
        raise ValueError("出力先はすでに存在します。別のパスを指定してください。")

    try:
        quality = int(min_quality.strip())
    except (ValueError, AttributeError):
        raise ValueError("最低 JPEG 品質は 1～100 の整数で入力してください。") from None
    if not 1 <= quality <= 100:
        raise ValueError("最低 JPEG 品質は 1～100 の整数で入力してください。")

    try:
        scale_percent = Decimal(min_scale_percent.strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("最低画像スケールは 0 より大きく 100 以下で入力してください。") from None
    if not scale_percent.is_finite() or not Decimal("0") < scale_percent <= Decimal("100"):
        raise ValueError("最低画像スケールは 0 より大きく 100 以下で入力してください。")
    min_scale = float(scale_percent / 100)
    if min_scale == 0.0:
        raise ValueError("最低画像スケールが小さすぎます。")

    return GuiRequest(
        input_path=source,
        output_path=destination,
        target_bytes=decimal_mb_to_bytes(target_mb),
        min_quality=quality,
        min_scale=min_scale,
        allow_small_searchable_text_rasterization=bool(
            allow_small_searchable_text_rasterization
        ),
    )


def build_simple_request(input_path: str | Path) -> GuiRequest:
    """Build the fixed, non-destructive-opt-in request used by every simple input."""
    source = Path(input_path)
    return build_request(
        str(source),
        str(suggest_output_path(source)),
        "10",
        str(SIMPLE_MIN_QUALITY),
        str(round(SIMPLE_MIN_SCALE * 100)),
        False,
    )


def run_request(
    request: GuiRequest,
    fitter: Callable[..., FitResult] = fit_pdf,
) -> FitResult:
    """Map a validated GUI request directly to the integrated backend API."""
    return fitter(
        request.input_path,
        request.output_path,
        target_bytes=request.target_bytes,
        min_quality=request.min_quality,
        min_scale=request.min_scale,
        allow_small_searchable_text_rasterization=(
            request.allow_small_searchable_text_rasterization
        ),
    )


def run_simple_input(
    input_path: str | Path,
    fitter: Callable[..., FitResult] = fit_pdf,
) -> FitResult:
    """Run a picker, GUI-drop, or shell-argument input through one request path."""
    return run_simple_request(build_simple_request(input_path), fitter=fitter)


def run_simple_request(
    request: GuiRequest,
    fitter: Callable[..., FitResult] = fit_pdf,
) -> FitResult:
    """Skip files at the exact simple limit; delegate only oversized PDFs."""
    input_size = request.input_path.stat().st_size
    if input_size <= SIMPLE_TARGET_BYTES:
        return FitResult(
            status=FitStatus.ALREADY_BELOW_TARGET,
            route=Route.SKIP,
            input_path=str(request.input_path),
            output_path=None,
            input_size_bytes=input_size,
            output_size_bytes=None,
            target_bytes=SIMPLE_TARGET_BYTES,
            delegated_route_status=None,
            reasons=(
                f"file size {input_size} is already at or below target "
                f"{SIMPLE_TARGET_BYTES}; no output was written",
            ),
        )
    return run_request(request, fitter=fitter)


def parse_drop_paths(
    data: str,
    splitlist: Callable[[str], Sequence[str]],
) -> tuple[Path, ...]:
    """Parse Tk DND data without requiring Tk or a graphical display in tests."""
    return tuple(Path(value) for value in splitlist(data))


def _format_size(value: int | None) -> str:
    if value is None:
        return "なし"
    return f"{value / 1_000_000:.3f} MB ({value:,} bytes)"


def present_simple_result(result: FitResult) -> ResultPresentation:
    details = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    if result.status is FitStatus.FITTED:
        output_size = result.output_size_bytes or 0
        summary_lines = [f"同じフォルダーに作成しました。\n{result.output_path}"]
        route_result = result.route_result
        selected_scale = getattr(route_result, "selected_scale", None)
        selected_quality = getattr(route_result, "selected_quality", None)
        if selected_scale is not None and selected_scale < 1.0:
            summary_lines.append("画像を縮小して変換しました。画質が低下している場合があります。")
            summary_lines.append(f"画像スケール: {selected_scale:.0%}")
            if selected_quality is not None:
                summary_lines.append(f"JPEG 品質: {selected_quality}")
        return ResultPresentation(
            category="fitted",
            title=(
                f"完了しました {result.input_size_bytes / 1_000_000:.1f} MB"
                f" -> {output_size / 1_000_000:.1f} MB"
            ),
            summary="\n".join(summary_lines),
            details=details,
            successful_output=Path(result.output_path) if result.output_path else None,
        )
    if result.status is FitStatus.ALREADY_BELOW_TARGET:
        return ResultPresentation(
            category="already-below-target",
            title=ALREADY_BELOW_MESSAGE,
            summary="出力ファイルは作成していません。",
            details=details,
        )
    if result.status is FitStatus.UNSUPPORTED_ROUTE:
        return ResultPresentation(
            category="unsupported-route",
            title="このPDFは安全に変換できませんでした。",
            summary="出力ファイルは作成していません。必要なら詳細設定を確認してください。",
            details=details,
        )

    delegated = result.delegated_route_status or "unknown"
    if delegated == "target-not-met":
        title = "10MB以下にできませんでした。"
        category = "target-not-met"
    else:
        title = "安全のため変換を中止しました。"
        category = "delegated-refusal"
    return ResultPresentation(
        category=category,
        title=title,
        summary="出力ファイルは作成していません。",
        details=details,
    )


def present_result(result: FitResult) -> ResultPresentation:
    details = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    if result.status is FitStatus.FITTED:
        summary = "\n".join(
            (
                "目標サイズ以下に変換しました。",
                f"入力サイズ: {_format_size(result.input_size_bytes)}",
                f"出力サイズ: {_format_size(result.output_size_bytes)}",
                f"診断ルート: {result.route.value}",
                f"出力先: {result.output_path}",
            )
        )
        return ResultPresentation(
            category="fitted",
            title="変換完了",
            summary=summary,
            details=details,
            successful_output=Path(result.output_path) if result.output_path else None,
        )
    if result.status is FitStatus.ALREADY_BELOW_TARGET:
        return ResultPresentation(
            category="already-below-target",
            title="処理は不要です",
            summary=(
                "入力 PDF はすでに目標サイズ以下です。出力ファイルは作成していません。\n"
                f"入力サイズ: {_format_size(result.input_size_bytes)}\n"
                f"診断ルート: {result.route.value}"
            ),
            details=details,
        )
    if result.status is FitStatus.UNSUPPORTED_ROUTE:
        return ResultPresentation(
            category="unsupported-route",
            title="未対応の PDF です",
            summary=(
                "対応する安全な処理ルートがありません。出力ファイルは作成していません。\n"
                f"診断ルート: {result.route.value}"
            ),
            details=details,
        )

    delegated = result.delegated_route_status or "unknown"
    if delegated == "target-not-met":
        title = "目標サイズに到達できませんでした"
        message = "指定した安全設定の範囲では目標サイズ以下にできませんでした。"
        category = "target-not-met"
    else:
        title = "安全のため処理を中止しました"
        message = "処理ルートが安全上の理由で拒否しました。"
        category = "delegated-refusal"
    return ResultPresentation(
        category=category,
        title=title,
        summary=(
            f"{message} 出力ファイルは作成していません。\n"
            f"診断ルート: {result.route.value}\n"
            f"処理ルートの状態: {delegated}"
        ),
        details=details,
    )


def present_error(error: BaseException) -> ResultPresentation:
    return ResultPresentation(
        category="unexpected-error",
        title="予期しないエラーが発生しました",
        summary="処理を完了できませんでした。入力 PDF は変更していません。",
        details=f"{type(error).__name__}: {error}",
    )


def present_validation_error(error: ValueError) -> ResultPresentation:
    return ResultPresentation(
        category="invalid-input",
        title="入力内容を確認してください",
        summary=str(error),
        details=f"ValueError: {error}",
    )


class _Application:
    def __init__(
        self,
        root: Any,
        tk: Any,
        ttk: Any,
        filedialog: Any,
        *,
        dnd_files: str | None = None,
        startup_input: str | Path | None = None,
    ) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.events: queue.Queue[tuple[str, Any, bool]] = queue.Queue()
        self.busy = False
        self.successful_output: Path | None = None
        self.advanced_visible = False

        root.title("PDF Size Fit")
        root.minsize(700, 440)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.target_var = tk.StringVar(value=DEFAULT_TARGET_MB)
        self.quality_var = tk.StringVar(value=DEFAULT_MIN_QUALITY)
        self.scale_var = tk.StringVar(value=DEFAULT_MIN_SCALE_PERCENT)
        self.allow_text_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="PDFをドロップするか、ファイルを選択してください。")

        frame = ttk.Frame(root, padding=20)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)

        self.drop_target = ttk.Label(
            frame,
            text="PDFをここにドロップ",
            anchor="center",
            padding=(30, 55),
            relief="solid",
        )
        self.drop_target.grid(row=0, column=0, sticky="nsew")
        if dnd_files is not None:
            self.drop_target.drop_target_register(dnd_files)
            self.drop_target.dnd_bind("<<Drop>>", self._on_drop)

        simple_actions = ttk.Frame(frame)
        simple_actions.grid(row=1, column=0, pady=12)
        self.pick_button = ttk.Button(
            simple_actions, text="PDFを選択…", command=self._choose_simple_input
        )
        self.pick_button.pack(side="left")
        self.details_button = ttk.Button(
            simple_actions, text="詳細設定", command=self._toggle_advanced
        )
        self.details_button.pack(side="left", padx=8)

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=2, column=0, sticky="ew")
        ttk.Label(
            frame,
            textvariable=self.status_var,
            wraplength=650,
            justify="center",
            anchor="center",
        ).grid(row=3, column=0, sticky="ew", pady=12)

        self.open_button = ttk.Button(
            frame, text="フォルダーを開く", command=self._open_folder, state="disabled"
        )
        self.open_button.grid(row=4, column=0)

        self.advanced = ttk.LabelFrame(frame, text="詳細設定", padding=12)
        self.advanced.grid(row=5, column=0, sticky="nsew", pady=(14, 0))
        self.advanced.columnconfigure(1, weight=1)
        self.advanced.rowconfigure(7, weight=1)
        self.advanced.grid_remove()
        self.advanced_controls: list[Any] = []
        self._build_advanced_controls()

        self.simple_controls = [self.pick_button, self.details_button, self.drop_target]
        if startup_input is not None:
            root.after(0, lambda: self._accept_simple_input(startup_input))

    def _build_advanced_controls(self) -> None:
        self.ttk.Label(self.advanced, text="入力 PDF").grid(
            row=0, column=0, sticky="w", pady=3
        )
        input_entry = self.ttk.Entry(self.advanced, textvariable=self.input_var)
        input_entry.grid(row=0, column=1, sticky="ew", padx=8)
        input_button = self.ttk.Button(
            self.advanced, text="選択…", command=self._choose_advanced_input
        )
        input_button.grid(row=0, column=2)
        self.ttk.Label(self.advanced, text="出力 PDF").grid(
            row=1, column=0, sticky="w", pady=3
        )
        output_entry = self.ttk.Entry(self.advanced, textvariable=self.output_var)
        output_entry.grid(row=1, column=1, sticky="ew", padx=8)
        output_button = self.ttk.Button(
            self.advanced, text="変更…", command=self._choose_output
        )
        output_button.grid(row=1, column=2)
        self.ttk.Label(self.advanced, text="目標サイズ (decimal MB)").grid(
            row=2, column=0, sticky="w", pady=3
        )
        target_entry = self.ttk.Entry(self.advanced, textvariable=self.target_var, width=12)
        target_entry.grid(row=2, column=1, sticky="w", padx=8)
        self.ttk.Label(self.advanced, text="最低 JPEG 品質").grid(
            row=3, column=0, sticky="w", pady=3
        )
        quality_entry = self.ttk.Entry(self.advanced, textvariable=self.quality_var, width=12)
        quality_entry.grid(row=3, column=1, sticky="w", padx=8)
        self.ttk.Label(self.advanced, text="最低画像スケール (%)").grid(
            row=4, column=0, sticky="w", pady=3
        )
        scale_entry = self.ttk.Entry(self.advanced, textvariable=self.scale_var, width=12)
        scale_entry.grid(row=4, column=1, sticky="w", padx=8)
        allow_check = self.ttk.Checkbutton(
            self.advanced,
            text="小量の検索可能テキストの画像化を許可する（明示的な破壊的 opt-in）",
            variable=self.allow_text_var,
        )
        allow_check.grid(row=5, column=0, columnspan=3, sticky="w", pady=5)
        run_button = self.ttk.Button(
            self.advanced, text="詳細設定で実行", command=self._start_advanced
        )
        run_button.grid(row=6, column=0, columnspan=3, sticky="w", pady=5)
        details_frame = self.ttk.Frame(self.advanced)
        details_frame.grid(row=7, column=0, columnspan=3, sticky="nsew")
        details_frame.columnconfigure(0, weight=1)
        details_frame.rowconfigure(0, weight=1)
        self.details = self.tk.Text(details_frame, height=10, wrap="word", state="disabled")
        scrollbar = self.ttk.Scrollbar(
            details_frame, orient="vertical", command=self.details.yview
        )
        self.details.configure(yscrollcommand=scrollbar.set)
        self.details.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.advanced_controls.extend(
            (
                input_entry,
                input_button,
                output_entry,
                output_button,
                target_entry,
                quality_entry,
                scale_entry,
                allow_check,
                run_button,
            )
        )

    def _ask_input(self) -> str:
        return self.filedialog.askopenfilename(
            title="入力 PDF を選択",
            filetypes=(("PDF files", "*.pdf"), ("All files", "*.*")),
        )

    def _choose_simple_input(self) -> None:
        selected = self._ask_input()
        if selected:
            self._accept_simple_input(selected)

    def _choose_advanced_input(self) -> None:
        selected = self._ask_input()
        if selected:
            self.input_var.set(selected)
            self.output_var.set(str(suggest_output_path(selected)))

    def _choose_output(self) -> None:
        initial = Path(self.output_var.get()) if self.output_var.get() else None
        selected = self.filedialog.asksaveasfilename(
            title="出力 PDF を指定",
            defaultextension=".pdf",
            filetypes=(("PDF files", "*.pdf"),),
            initialdir=str(initial.parent) if initial else None,
            initialfile=initial.name if initial else None,
            confirmoverwrite=False,
        )
        if selected:
            self.output_var.set(selected)

    def _on_drop(self, event: Any) -> None:
        if self.busy:
            return
        paths = parse_drop_paths(event.data, self.root.tk.splitlist)
        if len(paths) != 1:
            self._show(
                present_validation_error(ValueError("PDFを1つだけドロップしてください。"))
            )
            return
        self._accept_simple_input(paths[0])

    def _accept_simple_input(self, input_path: str | Path) -> None:
        try:
            request = build_simple_request(input_path)
        except ValueError as error:
            self._show(present_validation_error(error))
            return
        except Exception as error:
            self._show(present_error(error))
            return
        self.input_var.set(str(request.input_path))
        self.output_var.set(str(request.output_path))
        self._begin(request, simple=True)

    def _start_advanced(self) -> None:
        try:
            request = build_request(
                self.input_var.get(), self.output_var.get(), self.target_var.get(),
                self.quality_var.get(), self.scale_var.get(), self.allow_text_var.get(),
            )
        except ValueError as error:
            self._show(present_validation_error(error))
            return
        except Exception as error:
            self._show(present_error(error))
            return
        self._begin(request, simple=False)

    def _begin(
        self,
        request: GuiRequest,
        *,
        simple: bool,
    ) -> None:
        self.busy = True
        self.successful_output = None
        self.open_button.configure(state="disabled")
        for control in self.simple_controls + self.advanced_controls:
            control.configure(state="disabled")
        self.status_var.set(
            "PDFを確認しています…"
            if request.input_path.stat().st_size <= request.target_bytes
            else "10MB以下になるよう調整しています…"
        )
        self._set_details("")
        self.progress.start(12)
        threading.Thread(
            target=self._worker,
            args=(request, simple),
            daemon=True,
        ).start()
        self.root.after(100, self._poll)

    def _worker(
        self,
        request: GuiRequest,
        simple: bool,
    ) -> None:
        try:
            result = run_simple_request(request) if simple else run_request(request)
            self.events.put(("result", result, simple))
        except BaseException as error:
            self.events.put(("error", error, simple))

    def _poll(self) -> None:
        try:
            kind, value, simple = self.events.get_nowait()
        except queue.Empty:
            if self.busy:
                self.root.after(100, self._poll)
            return
        self.busy = False
        self.progress.stop()
        for control in self.simple_controls + self.advanced_controls:
            control.configure(state="normal")
        if kind == "result":
            presentation = (
                present_simple_result(value) if simple else present_result(value)
            )
        else:
            presentation = present_error(value)
        self._show(presentation)

    def _show(self, presentation: ResultPresentation) -> None:
        self.status_var.set(f"{presentation.title}\n{presentation.summary}")
        self._set_details(presentation.details)
        self.successful_output = presentation.successful_output
        self.open_button.configure(
            state="normal" if self.successful_output is not None else "disabled"
        )

    def _set_details(self, value: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", value)
        self.details.configure(state="disabled")

    def _toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced.grid()
            self.details_button.configure(text="詳細設定を閉じる")
            self.root.minsize(760, 760)
        else:
            self.advanced.grid_remove()
            self.details_button.configure(text="詳細設定")
            self.root.minsize(700, 440)

    def _open_folder(self) -> None:
        if self.successful_output is not None:
            os.startfile(str(self.successful_output.parent))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PDF Size Fit simple Windows GUI")
    parser.add_argument("pdf", nargs="?", help="Explorer からドロップした PDF")
    args = parser.parse_args(argv)

    # GUI dependencies are imported only at startup. Headless CI imports and tests
    # the complete simple workflow without Tk, a graphical display, or Windows DND.
    import tkinter as tk
    from tkinter import filedialog, ttk
    from tkinterdnd2 import DND_FILES, TkinterDnD

    root = TkinterDnD.Tk()
    _Application(
        root,
        tk,
        ttk,
        filedialog,
        dnd_files=DND_FILES,
        startup_input=args.pdf,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
