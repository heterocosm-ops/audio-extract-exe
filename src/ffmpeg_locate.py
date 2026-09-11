"""FFmpeg / FFprobe 실행 파일 경로를 찾는다.

우선순위:
1. PyInstaller로 빌드된 실행 파일에 함께 포함(bundle)된 ffmpeg.exe / ffprobe.exe
2. 실행 파일과 같은 폴더에 있는 ffmpeg.exe / ffprobe.exe
3. 시스템 PATH 에 등록된 ffmpeg / ffprobe
"""
from __future__ import annotations

import os
import shutil
import sys

IS_WINDOWS = sys.platform.startswith("win")
FFMPEG_NAME = "ffmpeg.exe" if IS_WINDOWS else "ffmpeg"
FFPROBE_NAME = "ffprobe.exe" if IS_WINDOWS else "ffprobe"


def _candidate_dirs() -> list[str]:
    dirs = []
    # PyInstaller onefile: 압축 해제된 임시 폴더
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(meipass)
        dirs.append(os.path.join(meipass, "bin"))
    # 실행 파일(또는 스크립트)이 있는 폴더
    exe_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    dirs.append(exe_dir)
    dirs.append(os.path.join(exe_dir, "bin"))
    # 이 소스 파일이 있는 폴더 (개발 중 실행할 때)
    src_dir = os.path.dirname(os.path.abspath(__file__))
    dirs.append(src_dir)
    dirs.append(os.path.join(src_dir, "bin"))
    return dirs


def _find(name: str) -> str | None:
    for d in _candidate_dirs():
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    found = shutil.which(os.path.splitext(name)[0])
    return found


def find_ffmpeg() -> str | None:
    return _find(FFMPEG_NAME)


def find_ffprobe() -> str | None:
    return _find(FFPROBE_NAME)
