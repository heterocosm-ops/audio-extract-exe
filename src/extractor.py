"""MP4 -> M4A 오디오 추출 핵심 로직 (GUI와 분리되어 단독 테스트 가능).

일본어 음성인식용 학습 자료 제작이 목적이므로, 원본 오디오 품질(샘플레이트/채널)을
임의로 낮추지 않는다. 가능하면 재인코딩 없이(-c:a copy) 스트림을 그대로 추출하고,
M4A 컨테이너가 지원하지 않는 코덱일 때만 고품질로 재인코딩한다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

from ffmpeg_locate import find_ffmpeg, find_ffprobe

# M4A(MP4) 컨테이너에 재인코딩 없이 그대로 담을 수 있는 오디오 코덱
COPY_COMPATIBLE_CODECS = {"aac", "alac"}

# 원본 파일보다 최소한 이만큼의 여유 공간(바이트)이 있어야 안전하다고 판단
DISK_SPACE_SAFETY_MARGIN = 10 * 1024 * 1024  # 10MB


class ExtractError(Exception):
    """추출 과정에서 발생하는 모든 오류의 기반 클래스. 한국어 메시지를 담는다."""


class FFmpegNotFoundError(ExtractError):
    pass


class NotMp4Error(ExtractError):
    pass


class CorruptedFileError(ExtractError):
    pass


class NoAudioTrackError(ExtractError):
    pass


class UnsupportedCodecError(ExtractError):
    pass


class WritePermissionError(ExtractError):
    pass


class DiskSpaceError(ExtractError):
    pass


class FFmpegExecutionError(ExtractError):
    pass


@dataclass
class AudioInfo:
    has_audio: bool
    codec_name: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bit_rate: int | None = None


@dataclass
class ExtractResult:
    output_path: str
    reencoded: bool
    audio_info: AudioInfo


def _startupinfo():
    """Windows 콘솔 창이 잠깐 뜨는 것을 막기 위한 설정."""
    if sys.platform.startswith("win"):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return si
    return None


def probe_media(input_path: str, ffprobe_path: str) -> dict:
    """ffprobe로 파일 정보를 JSON으로 가져온다. 손상된 파일이면 CorruptedFileError."""
    cmd = [
        ffprobe_path,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        input_path,
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=_startupinfo(),
            timeout=60,
        )
    except OSError as e:
        raise FFmpegNotFoundError(f"ffprobe 실행 파일을 실행할 수 없습니다: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise CorruptedFileError("파일 분석 시간이 초과되었습니다. 파일이 손상되었을 수 있습니다.") from e

    if proc.returncode != 0 or not proc.stdout.strip():
        stderr = proc.stderr.decode("utf-8", errors="ignore")
        raise CorruptedFileError(
            "파일을 읽을 수 없습니다. 올바른 동영상 파일인지, 손상되지 않았는지 확인해 주세요.\n"
            f"(상세: {stderr.strip()[-300:]})"
        )

    try:
        return json.loads(proc.stdout.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError as e:
        raise CorruptedFileError("파일 정보를 해석할 수 없습니다. 파일이 손상되었을 수 있습니다.") from e


def get_audio_info(probe_data: dict) -> AudioInfo:
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "audio":
            sample_rate = stream.get("sample_rate")
            return AudioInfo(
                has_audio=True,
                codec_name=stream.get("codec_name"),
                sample_rate=int(sample_rate) if sample_rate else None,
                channels=stream.get("channels"),
                bit_rate=int(stream["bit_rate"]) if stream.get("bit_rate") else None,
            )
    return AudioInfo(has_audio=False)


def check_is_mp4(input_path: str, probe_data: dict) -> None:
    # 파일 내용을 우선 검사한다. 확장자만 .mp4로 바뀐 다른 형식의 파일도 걸러낸다.
    fmt_name = probe_data.get("format", {}).get("format_name", "")
    if not any(tag in fmt_name for tag in ("mp4", "mov", "m4v")):
        raise NotMp4Error(
            "MP4 동영상 파일이 아닙니다. 실제 파일 형식을 확인해 주세요.\n"
            f"(감지된 형식: {fmt_name or '알 수 없음'})"
        )


def check_write_permission(output_dir: str) -> None:
    if not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            raise WritePermissionError(f"저장 폴더를 만들 수 없습니다: {e}") from e
    test_path = os.path.join(output_dir, ".write_test.tmp")
    try:
        with open(test_path, "wb") as f:
            f.write(b"0")
        os.remove(test_path)
    except OSError as e:
        raise WritePermissionError(
            f"저장 폴더에 쓰기 권한이 없습니다: {output_dir}\n다른 폴더를 선택해 주세요. ({e})"
        ) from e


def check_disk_space(output_dir: str, required_bytes: int) -> None:
    try:
        usage = shutil.disk_usage(output_dir)
    except OSError:
        return  # 확인 불가 시 통과시키고 실제 추출 단계에서 오류 처리
    if usage.free < required_bytes + DISK_SPACE_SAFETY_MARGIN:
        free_mb = usage.free / (1024 * 1024)
        need_mb = (required_bytes + DISK_SPACE_SAFETY_MARGIN) / (1024 * 1024)
        raise DiskSpaceError(
            f"디스크 여유 공간이 부족합니다. (여유 공간: {free_mb:.1f}MB, 필요 공간: 약 {need_mb:.1f}MB)"
        )


def build_output_path(input_path: str, output_dir: str) -> str:
    base = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(output_dir, f"{base}_audio.m4a")


def _run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=_startupinfo(),
            timeout=None,
        )
    except OSError as e:
        raise FFmpegNotFoundError(f"FFmpeg 실행 파일을 실행할 수 없습니다: {e}") from e


def extract_audio(
    input_path: str,
    output_dir: str,
    progress_callback=None,
) -> ExtractResult:
    """MP4에서 오디오만 추출해 output_dir 에 <원본이름>_audio.m4a 로 저장한다.

    가능하면 재인코딩 없이 그대로 복사하고, M4A가 지원하지 않는 코덱이면
    고품질로 재인코딩한다(샘플레이트/채널은 원본 그대로 유지).
    """

    def report(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    ffmpeg_path = find_ffmpeg()
    ffprobe_path = find_ffprobe()
    if not ffmpeg_path or not ffprobe_path:
        raise FFmpegNotFoundError(
            "FFmpeg를 찾을 수 없습니다. 프로그램 폴더에 ffmpeg.exe / ffprobe.exe 가 있는지 확인해 주세요."
        )

    if not os.path.isfile(input_path):
        raise CorruptedFileError("선택한 파일을 찾을 수 없습니다.")

    report("파일 분석 중...")
    probe_data = probe_media(input_path, ffprobe_path)
    check_is_mp4(input_path, probe_data)

    audio_info = get_audio_info(probe_data)
    if not audio_info.has_audio:
        raise NoAudioTrackError("이 동영상에는 오디오 트랙이 없습니다.")

    check_write_permission(output_dir)
    input_size = os.path.getsize(input_path)
    check_disk_space(output_dir, input_size)

    output_path = build_output_path(input_path, output_dir)

    reencoded = False
    if audio_info.codec_name in COPY_COMPATIBLE_CODECS:
        report("오디오 스트림을 원본 그대로 추출하는 중 (재인코딩 없음)...")
        cmd = [
            ffmpeg_path, "-y",
            "-i", input_path,
            "-vn",
            "-map", "0:a:0",
            "-c:a", "copy",
            output_path,
        ]
        proc = _run_ffmpeg(cmd)
        if proc.returncode != 0:
            report("원본 그대로 저장이 불가능하여 고품질로 재인코딩합니다...")
            proc = None  # fall through to re-encode
        else:
            proc = "ok"

    else:
        proc = None

    if proc != "ok":
        reencoded = True
        report("오디오를 고품질 AAC로 재인코딩하는 중...")
        cmd = [
            ffmpeg_path, "-y",
            "-i", input_path,
            "-vn",
            "-map", "0:a:0",
            "-c:a", "aac",
            "-b:a", "320k",
        ]
        if audio_info.sample_rate:
            cmd += ["-ar", str(audio_info.sample_rate)]
        if audio_info.channels:
            cmd += ["-ac", str(audio_info.channels)]
        cmd += ["-movflags", "+faststart", output_path]

        result = _run_ffmpeg(cmd)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            lowered = stderr.lower()
            if "codec not currently supported" in lowered or "unsupported codec" in lowered or "unknown codec" in lowered:
                raise UnsupportedCodecError(
                    f"지원하지 않는 오디오 코덱입니다 ({audio_info.codec_name}).\n(상세: {stderr.strip()[-300:]})"
                )
            if "no space left" in lowered:
                raise DiskSpaceError("디스크 공간이 부족하여 저장에 실패했습니다.")
            if "permission denied" in lowered:
                raise WritePermissionError("저장 폴더에 쓰기 권한이 없습니다.")
            raise FFmpegExecutionError(
                f"FFmpeg 실행 중 오류가 발생했습니다.\n(상세: {stderr.strip()[-500:]})"
            )

    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise FFmpegExecutionError("오디오 파일이 생성되지 않았습니다. 원본 파일을 확인해 주세요.")

    report("완료")
    return ExtractResult(output_path=output_path, reencoded=reencoded, audio_info=audio_info)


def human_size(num_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f}TB"
