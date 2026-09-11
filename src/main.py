"""MP4 오디오 추출기 - GUI 진입점.

MP4 동영상에서 오디오만 추출하여 M4A로 저장하는 아주 단순한 Windows 데스크톱
프로그램. 일본어 음성인식/받아쓰기용 원본 음질 보존이 목적이므로 가능하면
재인코딩 없이 오디오 스트림을 그대로 추출한다.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extractor import (  # noqa: E402
    CorruptedFileError,
    DiskSpaceError,
    ExtractError,
    FFmpegExecutionError,
    FFmpegNotFoundError,
    NoAudioTrackError,
    NotMp4Error,
    UnsupportedCodecError,
    WritePermissionError,
    extract_audio,
    human_size,
    probe_media,
    get_audio_info,
)
from ffmpeg_locate import find_ffprobe  # noqa: E402

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    HAS_DND = True
except ImportError:
    HAS_DND = False

APP_TITLE = "MP4 오디오 추출기"
WINDOW_SIZE = "560x430"


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(500, 400)

        self.input_path: str | None = None
        self.output_dir: str | None = None

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        title = tk.Label(self.root, text=APP_TITLE, font=("맑은 고딕", 18, "bold"))
        title.pack(pady=(16, 8))

        self.drop_frame = tk.LabelFrame(self.root, text="파일", padx=12, pady=12)
        self.drop_frame.pack(fill="x", padx=16, pady=8)

        drop_hint = "여기로 MP4 파일을 드래그하거나 아래 버튼을 눌러 선택하세요." if HAS_DND \
            else "아래 버튼을 눌러 MP4 파일을 선택하세요."
        self.drop_label = tk.Label(
            self.drop_frame, text=drop_hint, fg="#555555", wraplength=480, justify="left"
        )
        self.drop_label.pack(fill="x")

        select_btn = tk.Button(self.drop_frame, text="MP4 파일 선택", command=self.on_select_file)
        select_btn.pack(pady=(8, 0))

        if HAS_DND:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind("<<Drop>>", self.on_drop)

        info_frame = tk.LabelFrame(self.root, text="파일 정보", padx=12, pady=12)
        info_frame.pack(fill="x", padx=16, pady=8)

        self.name_var = tk.StringVar(value="원본 파일명: -")
        self.size_var = tk.StringVar(value="원본 파일 크기: -")
        self.audio_var = tk.StringVar(value="오디오 존재 여부: -")

        tk.Label(info_frame, textvariable=self.name_var, anchor="w", justify="left").pack(fill="x")
        tk.Label(info_frame, textvariable=self.size_var, anchor="w", justify="left").pack(fill="x")
        tk.Label(info_frame, textvariable=self.audio_var, anchor="w", justify="left").pack(fill="x")

        out_frame = tk.LabelFrame(self.root, text="저장 폴더", padx=12, pady=12)
        out_frame.pack(fill="x", padx=16, pady=8)

        self.out_var = tk.StringVar(value="저장 폴더: (파일을 선택하면 자동 지정)")
        tk.Label(out_frame, textvariable=self.out_var, anchor="w", justify="left", wraplength=380).pack(
            side="left", fill="x", expand=True
        )
        tk.Button(out_frame, text="폴더 선택", command=self.on_select_output_dir).pack(side="right")

        self.extract_btn = tk.Button(
            self.root, text="오디오 추출", font=("맑은 고딕", 12, "bold"),
            command=self.on_extract, state="disabled", height=2,
        )
        self.extract_btn.pack(fill="x", padx=16, pady=(12, 4))

        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", padx=16, pady=(0, 4))

        self.status_var = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.status_var, fg="#0a6b0a", wraplength=520, justify="left").pack(
            fill="x", padx=16, pady=(0, 12)
        )

    # ------------------------------------------------------------- actions
    def on_select_file(self) -> None:
        path = filedialog.askopenfilename(
            title="MP4 파일 선택",
            filetypes=[("MP4 동영상", "*.mp4"), ("모든 파일", "*.*")],
        )
        if path:
            self._load_file(path)

    def on_drop(self, event) -> None:
        # tkinterdnd2 는 경로를 중괄호로 감싸서 전달할 수 있음 (공백 포함 경로 대응)
        raw = event.data
        paths = self.root.tk.splitlist(raw)
        if paths:
            self._load_file(paths[0])

    def on_select_output_dir(self) -> None:
        initial = self.output_dir or os.getcwd()
        path = filedialog.askdirectory(title="저장 폴더 선택", initialdir=initial)
        if path:
            self.output_dir = path
            self.out_var.set(f"저장 폴더: {path}")

    def _load_file(self, path: str) -> None:
        ext = os.path.splitext(path)[1].lower()
        if ext != ".mp4":
            messagebox.showerror("파일 오류", "MP4 파일만 선택할 수 있습니다.")
            return
        if not os.path.isfile(path):
            messagebox.showerror("파일 오류", "선택한 파일을 찾을 수 없습니다.")
            return

        self.input_path = path
        self.output_dir = os.path.dirname(path)
        self.out_var.set(f"저장 폴더: {self.output_dir}")
        self.status_var.set("")

        size = os.path.getsize(path)
        self.name_var.set(f"원본 파일명: {os.path.basename(path)}")
        self.size_var.set(f"원본 파일 크기: {human_size(size)}")
        self.audio_var.set("오디오 존재 여부: 확인 중...")
        self.extract_btn.config(state="disabled")

        threading.Thread(target=self._probe_file, args=(path,), daemon=True).start()

    def _probe_file(self, path: str) -> None:
        ffprobe_path = find_ffprobe()
        try:
            if not ffprobe_path:
                raise FFmpegNotFoundError("FFmpeg(ffprobe)를 찾을 수 없습니다.")
            data = probe_media(path, ffprobe_path)
            info = get_audio_info(data)
        except ExtractError as e:
            self.root.after(0, self._probe_failed, str(e))
            return
        self.root.after(0, self._probe_done, info)

    def _probe_failed(self, message: str) -> None:
        self.audio_var.set("오디오 존재 여부: 확인 실패")
        messagebox.showerror("오류", message)

    def _probe_done(self, info) -> None:
        if info.has_audio:
            details = []
            if info.codec_name:
                details.append(f"코덱 {info.codec_name}")
            if info.sample_rate:
                details.append(f"{info.sample_rate}Hz")
            if info.channels:
                details.append(f"{info.channels}채널")
            extra = f" ({', '.join(details)})" if details else ""
            self.audio_var.set(f"오디오 존재 여부: 있음{extra}")
            self.extract_btn.config(state="normal")
        else:
            self.audio_var.set("오디오 존재 여부: 없음")
            self.extract_btn.config(state="disabled")
            messagebox.showwarning("오디오 없음", "이 동영상에는 오디오 트랙이 없습니다.")

    def on_extract(self) -> None:
        if not self.input_path or not self.output_dir:
            return
        self.extract_btn.config(state="disabled")
        self.status_var.set("추출 준비 중...")
        self.progress.start(12)
        threading.Thread(target=self._run_extract, daemon=True).start()

    def _run_extract(self) -> None:
        def report(msg: str) -> None:
            self.root.after(0, self.status_var.set, msg)

        try:
            result = extract_audio(self.input_path, self.output_dir, progress_callback=report)
        except ExtractError as e:
            self.root.after(0, self._extract_failed, e)
            return
        except Exception as e:  # noqa: BLE001 - 예상 못한 오류도 사용자에게 안내
            self.root.after(0, self._extract_failed, e)
            return
        self.root.after(0, self._extract_done, result)

    def _extract_failed(self, error: Exception) -> None:
        self.progress.stop()
        self.extract_btn.config(state="normal")
        self.status_var.set("")
        title_map = {
            NotMp4Error: "파일 형식 오류",
            CorruptedFileError: "파일 손상",
            NoAudioTrackError: "오디오 없음",
            UnsupportedCodecError: "지원하지 않는 코덱",
            WritePermissionError: "권한 오류",
            DiskSpaceError: "디스크 공간 부족",
            FFmpegExecutionError: "FFmpeg 오류",
            FFmpegNotFoundError: "FFmpeg 없음",
        }
        title = title_map.get(type(error), "오류")
        messagebox.showerror(title, str(error))

    def _extract_done(self, result) -> None:
        self.progress.stop()
        self.extract_btn.config(state="normal")
        mode = "재인코딩(고품질 AAC)" if result.reencoded else "재인코딩 없이 원본 그대로"
        self.status_var.set(
            f"추출 완료 ({mode})\n저장 위치: {result.output_path}"
        )
        if messagebox.askyesno("추출 완료", f"저장 위치:\n{result.output_path}\n\n폴더를 여시겠습니까?"):
            self._open_folder(result.output_path)

    @staticmethod
    def _open_folder(file_path: str) -> None:
        folder = os.path.dirname(file_path)
        try:
            if sys.platform.startswith("win"):
                subprocess.run(["explorer", "/select,", file_path])
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", file_path])
            else:
                subprocess.run(["xdg-open", folder])
        except OSError:
            pass


def main() -> None:
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
