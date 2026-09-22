# 돌봄(DolBom)

요양보호사가 병실 CCTV, 표준 운동 영상, 보행 촬영을 한 화면에서 다루는 **PyQt6 데스크톱 프로그램**입니다.

클라이언트에는 AI 모델을 두지 않습니다. YOLO·자세·스켈레톤·낙상 판정은 메인 서버의 역할이며, 이 앱은 영상 수집·전송과 서버 메시지 표시만 합니다. 회원가입·REST API·웹 서버는 포함하지 않습니다.

## 실행 환경

- Python 3.10 이상
- PyQt6, OpenCV, NumPy

```bash
python3 -m pip install -r requirements.txt
python3 -m dolbom
```

Linux에서 Qt 창이 뜨지 않으면:

```bash
sudo apt install libegl1 libxkbcommon-x11-0 libxcb-cursor0
```

데모 모드를 강제로 켜려면:

```bash
python3 -m dolbom --demo
```

프로토콜 검증용 시험 수신기를 따로 띄울 때(앱 설정에서 내장 수신기를 끈 경우):

```bash
python3 -m dolbom.tools.test_receiver --tcp 45757 --udp 45004
```

테스트:

```bash
python3 -m pytest
```

데이터는 기본적으로 사용자 앱 데이터 폴더(`~/.local/share/dolbom` 등)의 SQLite에 저장됩니다. 테스트는 `DOLBOM_DATA_DIR`로 격리합니다.

## 기존 프로젝트

이 저장소는 빈 저장소에서 시작했습니다. Qt 바인딩이 없어 **PyQt6**를 사용합니다.

## 화면 구성

공통 상단: 앱 이름, 제어 채널 상태, 현재 시각  
좌측 메뉴: 병실 CCTV · 운동 · 보행 · 설정 (`Ctrl+1`~`4`)  
하단 알림: 미확인 수, 최신 요약, 중요도, 전체 메시지(`Ctrl+M`)

메뉴를 바꿔도 CCTV 수집·전송과 메시지 수신은 유지됩니다.

| 버튼 | 의미 |
| --- | --- |
| 전송 시작 | 해당 카메라 영상을 서버(또는 시험 수신기)로 보내기 시작 |
| 전송 종료 | CCTV 전송만 끝냄. 수집은 계속 |
| 세션 종료 | 운동·보행 세션과 그 전송을 끝냄 |
| 재생 / 일시정지 | 표준 운동 영상 플레이어 전용. 세션 일시정지는 없음 |

## 미디어 백엔드

**OpenCV 수집 + JPEG RTP/UDP 전송 + Qt Multimedia(HTTPS) / OpenCV(로컬 재생)** 하나를 골랐습니다.

- 카메라 읽기와 JPEG 인코딩은 작업 스레드에서만 수행합니다.
- 큰 원본 프레임을 단일 UDP 패킷으로 보내지 않습니다. RFC 2435 형식의 JPEG RTP로 조각화합니다(조각 최대 1200바이트).
- GStreamer 전용 파이프라인에 의존하지 않아 Windows/macOS/Linux에서 설치 면이 단순합니다.
- 로컬 표준 영상은 OpenCV 플레이어, HTTPS 직접 미디어 URL은 `QMediaPlayer`로 재생합니다.
- 유튜브·Physitrack 같은 웹페이지 URL은 내부 재생을 보장하지 않으며, 이유와 「브라우저에서 열기」를 제공합니다. 다운로드 우회는 없습니다.

이 전송 형식은 **시험용 transport**이며 생산 메인 서버 코덱 합의가 아닙니다.

## 제어·메시지 프로토콜 (초안)

기존 서버 규격이 없어 `dolbom/protocol.py`에 최소 초안을 두었습니다. TCP로 **4바이트 big-endian 길이 + UTF-8 JSON**을 주고받습니다.

클라이언트 → 서버: `hello`, `session.start`, `session.end`, `status`, `sync.request`, `ping`  
서버 → 클라이언트: `hello.ack`, `event`, `session.sync`, `pong`, `error`

세션 메타데이터: `stream_id`, `session_id`, `mode`(cctv/exercise/gait), `patient_id`, `playlist_item_id`, 사용자가 등록한 제목·토픽.

연결이 되어도 UI에는 「메인 서버 연동 완료」라고 쓰지 않습니다. 내장 수신기는 **「시험 수신기 연결됨」**, 그 외는 **「제어 채널 연결됨 (초안 프로토콜)」**입니다.

## 데모 모드

기본값은 데모 모드입니다.

- 카메라는 `DEMO — not a live camera`가 적힌 합성 영상입니다.
- 로컬 시험 수신기가 TCP 45757 / UDP 45004를 엽니다.
- 상단에 데모·시험 수신기 안내가 항상 보입니다.

설정에서 데모 모드와 시험 수신기를 끄고 실제 장치 번호·RTSP·서버 주소를 넣을 수 있습니다.

## 저장 범위

SQLite에 카메라, 재생목록·토픽, 연결 설정, 세션 이력, 메시지 이력, 대상자 이름·병실만 저장합니다.  
원본 영상 녹화·보관은 하지 않습니다. 재생목록 삭제는 목록에서만 제거합니다. 로그에 환자 정보와 카메라 비밀번호를 남기지 않습니다.

## 검증 결과

자동 테스트 15개 통과 (`pytest`). GUI 통합 점검에서 확인한 항목:

- 메뉴를 바꿔도 CCTV 수집 스레드가 유지됨
- 카메라 3대 추가는 DB·화면만으로 가능 (코드의 카메라 수 고정 없음)
- 운동 세션 중 보행 시작은 기존 세션 종료를 요구함
- 로컬 표준 영상 재생, 재생목록·토픽이 SQLite에 유지됨
- 시험 수신기로 UDP 패킷·TCP 세션 메시지를 수신함
- 앱 종료 시 수집·전송·제어 스레드를 정리함

## 실제 장비·서버가 있어야 확인 가능한 항목

- USB/내장 웹캠, RTSP CCTV의 실제 화질과 재연결
- 생산 메인 서버와의 프로토콜·RTP 호환
- 서버가 보내는 실제 낙상 등 긴급 이벤트 연동
- HTTPS 직접 미디어의 코덱별 재생
- 알림 소리와 현장 스피커
