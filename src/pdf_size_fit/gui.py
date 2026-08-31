from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from .fit import FitResult, FitStatus, fit_pdf


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


def _format_size(value: int | None) -> str:
    if value is None:
        return "なし"
    return f"{value / 1_000_000:.3f} MB ({value:,} bytes)"


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
    def __init__(self, root: Any, tk: Any, ttk: Any, filedialog: Any) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False
        self.successful_output: Path | None = None

        root.title("PDF Size Fit")
        root.minsize(760, 620)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.target_var = tk.StringVar(value=DEFAULT_TARGET_MB)
        self.quality_var = tk.StringVar(value=DEFAULT_MIN_QUALITY)
        self.scale_var = tk.StringVar(value=DEFAULT_MIN_SCALE_PERCENT)
        self.allow_text_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="入力 PDF を選択してください。")

        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(9, weight=1)

        self.controls: list[Any] = []
        row = 0
        ttk.Label(frame, text="入力 PDF").grid(row=row, column=0, sticky="w", pady=4)
        input_entry = ttk.Entry(frame, textvariable=self.input_var)
        input_entry.grid(row=row, column=1, sticky="ew", padx=8)
        input_button = ttk.Button(frame, text="選択…", command=self._choose_input)
        input_button.grid(row=row, column=2)
        self.controls.extend((input_entry, input_button))

        row += 1
        ttk.Label(frame, text="出力 PDF").grid(row=row, column=0, sticky="w", pady=4)
        output_entry = ttk.Entry(frame, textvariable=self.output_var)
        output_entry.grid(row=row, column=1, sticky="ew", padx=8)
        output_button = ttk.Button(frame, text="変更…", command=self._choose_output)
        output_button.grid(row=row, column=2)
        self.controls.extend((output_entry, output_button))

        row += 1
        ttk.Label(frame, text="目標サイズ (decimal MB)").grid(
            row=row, column=0, sticky="w", pady=4
        )
        target_entry = ttk.Entry(frame, textvariable=self.target_var, width=12)
        target_entry.grid(row=row, column=1, sticky="w", padx=8)
        ttk.Label(frame, text="1 MB = 1,000,000 bytes").grid(row=row, column=2, sticky="w")
        self.controls.append(target_entry)

        row += 1
        ttk.Label(frame, text="最低 JPEG 品質").grid(row=row, column=0, sticky="w", pady=4)
        quality_entry = ttk.Entry(frame, textvariable=self.quality_var, width=12)
        quality_entry.grid(row=row, column=1, sticky="w", padx=8)
        self.controls.append(quality_entry)

        row += 1
        ttk.Label(frame, text="最低画像スケール (%)").grid(
            row=row, column=0, sticky="w", pady=4
        )
        scale_entry = ttk.Entry(frame, textvariable=self.scale_var, width=12)
        scale_entry.grid(row=row, column=1, sticky="w", padx=8)
        ttk.Label(frame, text="100% のままなら縮小しません").grid(
            row=row, column=2, sticky="w"
        )
        self.controls.append(scale_entry)

        row += 1
        allow_check = ttk.Checkbutton(
            frame,
            text="小量の検索可能テキストのラスタライズを許可する（明示的な破壊的 opt-in）",
            variable=self.allow_text_var,
        )
        allow_check.grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        self.controls.append(allow_check)

        row += 1
        action_frame = ttk.Frame(frame)
        action_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        self.run_button = ttk.Button(action_frame, text="実行", command=self._start)
        self.run_button.pack(side="left")
        self.controls.append(self.run_button)
        self.open_button = ttk.Button(
            action_frame, text="出力フォルダーを開く", command=self._open_folder, state="disabled"
        )
        self.open_button.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(action_frame, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(8, 0))

        row += 1
        ttk.Label(frame, textvariable=self.status_var, wraplength=710, justify="left").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=8
        )

        row += 1
        ttk.Label(frame, text="詳細（バックエンドの判定根拠）").grid(
            row=row, column=0, columnspan=3, sticky="w"
        )
        row += 1
        details_frame = ttk.Frame(frame)
        details_frame.grid(row=row, column=0, columnspan=3, sticky="nsew")
        details_frame.columnconfigure(0, weight=1)
        details_frame.rowconfigure(0, weight=1)
        self.details = tk.Text(details_frame, height=14, wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(details_frame, orient="vertical", command=self.details.yview)
        self.details.configure(yscrollcommand=scrollbar.set)
        self.details.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def _choose_input(self) -> None:
        selected = self.filedialog.askopenfilename(
            title="入力 PDF を選択",
            filetypes=(("PDF files", "*.pdf"), ("All files", "*.*")),
        )
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

    def _start(self) -> None:
        try:
            request = build_request(
                self.input_var.get(),
                self.output_var.get(),
                self.target_var.get(),
                self.quality_var.get(),
                self.scale_var.get(),
                self.allow_text_var.get(),
            )
        except ValueError as error:
            self._show(present_validation_error(error))
            return
        except Exception as error:
            self._show(present_error(error))
            return

        self.busy = True
        self.successful_output = None
        self.open_button.configure(state="disabled")
        for control in self.controls:
            control.configure(state="disabled")
        self.status_var.set("処理中です…")
        self._set_details("")
        self.progress.start(12)
        threading.Thread(target=self._worker, args=(request,), daemon=True).start()
        self.root.after(100, self._poll)

    def _worker(self, request: GuiRequest) -> None:
        try:
            self.events.put(("result", run_request(request)))
        except BaseException as error:
            self.events.put(("error", error))

    def _poll(self) -> None:
        try:
            kind, value = self.events.get_nowait()
        except queue.Empty:
            if self.busy:
                self.root.after(100, self._poll)
            return
        self.busy = False
        self.progress.stop()
        for control in self.controls:
            control.configure(state="normal")
        presentation = present_result(value) if kind == "result" else present_error(value)
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

    def _open_folder(self) -> None:
        if self.successful_output is not None:
            os.startfile(str(self.successful_output.parent))


def main() -> None:
    # Tk is deliberately imported only at GUI startup so headless CI can import
    # and test all non-visual helpers without Tk being installed.
    import tkinter as tk
    from tkinter import filedialog, ttk

    root = tk.Tk()
    _Application(root, tk, ttk, filedialog)
    root.mainloop()


if __name__ == "__main__":
    main()
