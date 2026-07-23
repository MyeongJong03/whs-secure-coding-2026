# Secure Market

교육용 중고 거래 애플리케이션을 안전한 SDLC 절차로 재구성하는 프로젝트다. Phase 03
상품·이미지·검색 기능은 `phase-03-products-search` 태그로 보존되어 있고, 현재 브랜치는
Phase 04 전체·1대1 실시간 채팅을 구현한다. 전체 과제는 아직 완료되지 않았다.

## 기준선

- 강사 스타터: `f0dd4baac057f62315bb4850f05d18b7e60eb4be`
- 강사 코드 태그: `course-starter-f0dd4ba`
- Phase 01 태그: `phase-01-foundation`
- Phase 02 태그: `phase-02-auth-users`
- Phase 03 태그: `phase-03-products-search`

## 현재 구현 상태

Phase 01~03의 인증·사용자·상품·이미지·검색 회귀를 유지한다. Phase 04에서는 다음 기능을
추가했다.

- active 인증 사용자 전용 전체 실시간 채팅과 저장 이력
- active 사용자 사이의 canonical 1대1 대화 생성·재사용과 참여자 전용 접근
- 최신 50개부터 역방향으로 탐색하는 SQL history pagination
- Socket connect CSRF, same-origin, 연결·이벤트별 active/auth_version 재검증
- 서버 인증 사용자만 발신자로 사용하는 sender spoof 방어
- per-app 연결 registry, 사용자당 5개 cap과 logout/password/dormant/age stale disconnect
- 전체·1대1 합산 사용자 message sliding-window limit과 join limit
- strict event schema, NFC/CRLF/control/문자·UTF-8 byte 검증과 transaction 후 broadcast
- Jinja autoescape와 browser `textContent`만 사용하는 저장 XSS 방어
- SHA-384를 확인한 local self-hosted Socket.IO browser client 4.8.3

일반 사용자의 history에서는 `is_hidden=True` 메시지를 제외하지만 실제 hide/delete 기능은
Phase 05 관리자 범위다. 대화 상대가 dormant면 기존 이력은 참여자에게만 보이고 신규 전송은
거부된다.

아직 구현하지 않은 기능:

- Phase 05: 신고·자동 제재·관리자 UI와 관리자 복구
- Phase 06: 가상 포인트 송금과 최종 통합

가상 포인트는 과제용 정수이며 실제 금융 자산이나 결제 수단이 아니다.

## 상품 이미지 정책

전체 HTTP 요청은 기존 5 MiB, 이미지 입력과 재인코딩 결과는 각각 4 MiB로 제한한다.
가로·세로는 각각 4096px, 총 pixel은 16,000,000 이하만 허용한다. 확장자는 UX나 신뢰
기준이 아니며 Pillow가 확인한 실제 JPEG, PNG, WebP format과 일치해야 한다. GIF, SVG,
BMP, TIFF, ICO, animation, 손상·truncated 파일, polyglot 뒤쪽 payload와 metadata는
저장하지 않는다.

기본 저장 위치는 `instance/uploads/products`다. 디렉터리는 `0700`, 파일은 `0600`이고
`app/static` 아래에 업로드를 두지 않는다. 원본 파일명은 저장명, DB, HTML, 응답 header나
로그에 기록하지 않는다. 저장명은 32자리 소문자 hex와 정규화 확장자다. 이미지 route는
DB filename도 재검증한다. configured upload root는 `resolve()`로 symlink를 따라가지 않고
`lstat` 결과와 직접 연 directory descriptor의 `fstat` inode identity를 비교한다. 생성·읽기·
삭제는 이 descriptor에 대한 상대 filename과 가능한 `O_NOFOLLOW`만 사용한다. 읽을 때는
regular-file·byte·실제 format뿐 아니라 현재 설정의 가로·세로·총 pixel 제한도 다시 검사한다.

Crash 시 DB commit 전에 저장됐지만 cleanup 전에 프로세스가 종료되어 생길 수 있는 고아
파일은 후속 유지보수 작업 대상이며, 현재 Phase에서 자동 삭제 사건이 있었다고 가정하지
않는다.

## 설정과 실행

시스템·전역 환경 대신 저장소의 `.venv`만 사용한다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/bootstrap_env.py
.venv/bin/flask --app run.py db upgrade
.venv/bin/python run.py
```

bootstrap script는 `.env.example`의 placeholder 한 곳을 새로운 무작위 Secret Key로
교체해 mode `0600`인 `.env`를 만든다. Secret Key 값은 화면에 출력하지 않으며 기존 `.env`가
있으면 덮어쓰지 않고 실패한다. 성공한 실행 뒤 `http://127.0.0.1:5000`에 접속한다.

Development·Production의 `SECRET_KEY`는 32자 이상 무작위 값이어야 한다. 상품의 기본
`PRODUCT_UPLOAD_DIR`, `PRODUCT_MAX_FILE_BYTES`, `PRODUCT_MAX_DIMENSION`,
`PRODUCT_MAX_PIXELS` 값은 `app/config.py`에 있다. 현재 구현은 `PRODUCT_*`를 환경변수에서
자동으로 읽지 않는다. custom 값은 `create_app(..., test_config={...})` 또는 애플리케이션
초기화 시 명시적인 Flask config로 주입할 수 있으며 테스트는 독립 tmp upload root를
사용한다. `.env`, `instance`, DB와 upload 파일은 Git에서 제외한다.

채팅의 history/conversation page 크기, message 문자·byte, burst/hour/join, 연결 cap과
socket 최대 나이는 `CHAT_*` Flask config로 정의한다. 테스트는 낮은 limit과 monotonic clock을
주입하며 CSRF를 비활성화하지 않는다. 메모리 registry와 event limiter는 단일 process
범위이므로 다중 process 배포에서는 외부 shared store와 process 간 disconnect 전달 계층이
필요하다.

## migration

- `09357cac1cb7`: 안전한 기반 모델
- `57c21fbc6f83`: 사용자 `auth_version`
- `c3d57de11bfa`: `ck_products_price_range`, `uq_products_image_filename`,
  공개/판매자/가격 named index
- `a91f4c8d2e70`: chat `is_hidden` boolean CHECK와 message/direct history용 named index 4개

네 번째 migration은 보존된 기존 세 파일을 수정하지 않는다. downgrade는 네 index와 새
boolean CHECK만 제거하고 기존 chat table·column·body CHECK·canonical 대화 제약과 FK는
유지한다.

## route

| Method | 경로 | 접근 |
|---|---|---|
| GET | `/products` | 공개 목록·검색 |
| GET | `/products/<uuid>` | 공개 active/sold 상세 |
| GET | `/products/<uuid>/image` | 공개 상품 또는 비공개 상품 소유자 |
| GET/POST | `/products/new` | 인증 사용자 상품 등록 |
| GET | `/me/products` | 본인 모든 상태 상품 |
| GET/POST | `/me/products/<uuid>/edit` | 본인 active/sold 수정 |
| POST | `/me/products/<uuid>/status` | 본인 active/sold 전이 |
| POST | `/me/products/<uuid>/delete` | 본인 상품 soft delete |
| GET | `/chat` | 인증 사용자의 전체 history; page 1만 live |
| GET | `/chat/direct` | 본인 1대1 대화 목록과 시작 form |
| POST | `/chat/direct/start` | username으로 active 상대 대화 생성·재사용 |
| GET | `/chat/direct/<uuid>` | 두 참여자만 history; page 1만 live |

모든 HTTP POST는 CSRF와 인증을 요구하고 성공 시 303을 반환한다. 채팅 HTTP 화면은
`no-store, private`다. 목록·검색은 IP당 60/minute, 상세·이미지는 120/minute, 생성은
사용자당 10/hour, 수정·상태·삭제는 endpoint별 30/hour다.

Socket.IO namespace는 `/chat`이다.

| Inbound event | 서버 처리 |
|---|---|
| `chat:join_global` | payload 없음/빈 객체만 허용하고 server global room join |
| `chat:join_direct` | canonical conversation UUID와 참여자 권한 확인 후 server room join |
| `chat:send_global` | joined global room, message 검증·저장 후 global room broadcast |
| `chat:send_direct` | joined direct room, 참여자·상대 active 재확인 후 해당 room broadcast |

outbound는 `chat:message`이며 sender username/body/server timestamp만 포함한다. client의
username, user ID, sender ID, auth version이나 room name은 받거나 신뢰하지 않는다.

## Local Socket.IO client

브라우저 bundle은 `app/static/vendor/socket.io-4.8.3.min.js`에서 self-host한다. 공식
`https://cdn.socket.io/4.8.3/socket.io.min.js`를 한 번 취득해 SHA-384 base64
`kzavj5fiMwLKzzD1f8S7TeoVIEi7uKHvbTA3ueZkrzYq75pNQUiUi6Dy98Q3fxb0`와 일치한 byte만 저장했다.
template의 local URL에 동일한 SRI를 적용하고 runtime CDN은 사용하지 않는다. 라이선스와
취득 정보는 `THIRD_PARTY_NOTICES.md`에 있다.

## 검증

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pytest --cov=app --cov-report=term-missing
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/bandit -q -r app scripts run.py
PIP_NO_CACHE_DIR=1 .venv/bin/pip-audit -r requirements.txt
PIP_NO_CACHE_DIR=1 .venv/bin/pip-audit -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -m compileall -q app scripts tests run.py
git diff --check
git status --short
```

coverage는 현재 `app` 코드 범위이며 미구현 Phase 05~06을 포함한 전체 과제 coverage가
아니다. pytest는 CSRF와 rate limit을 비활성화하지 않고 외부 네트워크에 의존하지 않는다.

## 구조

```text
app/auth/                 인증 form, route, service
app/users/                사용자 form, route, service
app/products/             상품 form, route, service, image, policy
app/chat/                 HTTP route, Socket event, service, registry, limiter, DTO
app/templates/chat/       전체·1대1 history와 local client 화면
app/static/js/chat.js     textContent 기반 실시간 browser 동작
app/static/vendor/        검증·고정된 Socket.IO browser client
app/templates/products/   공개·소유자 상품 화면
app/models/               SQLAlchemy 모델과 DB 제약
migrations/versions/      네 개의 순차 Alembic revision
scripts/bootstrap_env.py   기존 파일을 덮어쓰지 않는 로컬 환경 bootstrap
tests/                    기존 회귀와 HTTP·DB·Socket·room·static integrity
docs/                     요구사항, 설계, 위협, Finding, 테스트와 증거 계획
```

외부 runtime CDN, inline script/style, Jinja `safe`/Markup을 사용하지 않는다. 신고·자동
제재·관리자 UI·관리자 message hide와 송금은 Phase 05~06 미구현 범위다.
