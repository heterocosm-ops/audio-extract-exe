# MP4 오디오 추출기

MP4 동영상에서 영상은 버리고 오디오만 고품질로 추출하여 **M4A** 파일로 저장하는
Windows용 프로그램입니다. 일본어 동영상의 음성을 AI 음성인식(받아쓰기)에 넣어
학습 교재를 만드는 용도로 설계되었습니다.

- 가능하면 오디오를 **재인코딩 없이 그대로 복사**해서 음질 손실이 없습니다.
  (원본이 AAC/ALAC이면 `-c:a copy` 로 그대로 추출)
- M4A가 지원하지 않는 코덱(mp3, opus 등)일 때만 고품질 AAC(320kbps)로 재인코딩하며,
  이때도 **원본 샘플레이트와 채널 수를 그대로 유지**합니다.
- FFmpeg 실행 파일이 프로그램 안에 포함되어 있어 **FFmpeg를 따로 설치할 필요가 없습니다.**

## 사용법

1. `MP4오디오추출기.exe` 를 더블클릭해서 실행합니다. (설치 과정 없음)
2. `[MP4 파일 선택]` 버튼을 누르거나, MP4 파일을 창 위로 드래그 앤 드롭합니다.
3. 파일 정보(파일명, 크기, 오디오 존재 여부)가 자동으로 표시됩니다.
4. 필요하면 `[폴더 선택]`으로 저장 위치를 바꿉니다. (기본값: 원본과 같은 폴더)
5. `[오디오 추출]` 버튼을 누릅니다.
6. "추출 완료" 메시지와 함께 저장된 M4A 파일 경로가 표시됩니다.
   - 예: `example.mp4` → `example_audio.m4a`

## 오류 메시지 안내

| 상황 | 메시지 |
|---|---|
| MP4가 아닌 파일 | "MP4 동영상 파일이 아닙니다." |
| 파일 손상 | "파일을 읽을 수 없습니다. 올바른 동영상 파일인지 확인해 주세요." |
| 오디오 트랙 없음 | "이 동영상에는 오디오 트랙이 없습니다." |
| 지원하지 않는 코덱 | "지원하지 않는 오디오 코덱입니다." |
| 저장 폴더 쓰기 권한 없음 | "저장 폴더에 쓰기 권한이 없습니다." |
| 디스크 공간 부족 | "디스크 여유 공간이 부족합니다." |
| FFmpeg 실행 실패 | "FFmpeg 실행 중 오류가 발생했습니다." |

## 프로젝트 구조

```
src/
  main.py            GUI (tkinter + 드래그앤드롭)
  extractor.py        MP4 -> M4A 추출 핵심 로직 (GUI와 분리, 단독 테스트 가능)
  ffmpeg_locate.py     번들된/시스템 FFmpeg 실행 파일 경로 탐색
requirements.txt      Python 의존성 (tkinterdnd2, pyinstaller)
.github/workflows/build-windows.yml   GitHub Actions로 Windows EXE 자동 빌드
```

## EXE 빌드 방법

이 저장소는 GitHub Actions로 Windows EXE를 **자동으로 빌드**합니다.
`main` 브랜치의 `src/` 변경 사항이 푸시되면 워크플로가 실행되어
공식 FFmpeg Windows 빌드([gyan.dev](https://www.gyan.dev/ffmpeg/builds/), FFmpeg
공식 다운로드 페이지에 안내된 배포처)를 내려받아 함께 포함한 뒤
PyInstaller로 `MP4오디오추출기.exe` 하나짜리 실행 파일을 만듭니다.

빌드 결과물은 GitHub Actions 실행 화면의 **Artifacts** 에서 내려받을 수 있습니다.

### 직접 빌드하기 (Windows PC, Python 설치되어 있을 때)

```powershell
pip install -r requirements.txt
# ffmpeg.exe, ffprobe.exe 를 https://www.gyan.dev/ffmpeg/builds/ 에서 받아
# src\bin\ 폴더에 넣은 뒤 실행:
pyinstaller --noconfirm --clean --onefile --windowed --name "MP4오디오추출기" ^
  --add-binary "src\bin\ffmpeg.exe;." --add-binary "src\bin\ffprobe.exe;." ^
  --paths src src\main.py
```

빌드된 EXE는 `dist\MP4오디오추출기.exe` 에 생성됩니다.

## 개발 중 직접 실행 (Python 필요)

```bash
pip install -r requirements.txt
python src/main.py
```
