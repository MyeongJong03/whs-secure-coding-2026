# Secure Market

교육용 중고거래 애플리케이션을 안전한 SDLC 절차로 재구성한 프로젝트다. Phase 01~05의
인증·사용자·상품·검색·채팅·신고·자동 제재·관리자 기능을 유지하면서 Phase 06의 사용자 간
가상 포인트 송금과 최종 보안 통합을 구현했다.

- Public repository: <https://github.com/MyeongJong03/whs-secure-coding-2026>
- Default branch: `main`
- 최종 구현 작업 branch: `phase/06-wallet-final`
- 최종 검증 후 사용할 보존 tag: `phase-06-wallet-final`

## 강사 제공 기준선

- Course starter repository: <https://github.com/ugonfor/secure-coding>
- Baseline commit: `f0dd4baac057f62315bb4850f05d18b7e60eb4be`
- 보존 tag: `course-starter-f0dd4ba`

이 프로젝트는 위 강사 제공 기준선에서 보안 요구사항과 구현을 재설계했다.

## 구현 기능

- 안전한 회원가입·로그인·로그아웃·비밀번호 변경과 dormant 세션 무효화
- 사용자·상품 검색, 안전한 이미지 업로드, 상품 소유권·상태 관리
- 전체·1대1 실시간 채팅, 참여자 권한, 서버 결정 sender/room과 rate limit
- 사용자·상품 신고, 서로 다른 신고자 3명 threshold 자동 제재
- CLI-only admin 생성, 관리자 재인증·상태 조치·감사 로그
- 사용자·관리자 간 과제용 가상 포인트 송금, 이력·상세와 관리자 읽기 전용 조회
- Alembic revision 6개, 90% app coverage gate와 GitHub Actions CI

본 프로젝트의 포인트는 과제용 가상 포인트다. 실제 금융 자산, 현금 또는 결제 수단이
아니며 은행·카드·결제·환전·충전·출금·환불 기능은 제공하지 않는다.

## Wallet·Transfer 보안 정책

회원가입과 `create-admin` CLI는 User와 초기 `Wallet(balance=100000)`을 같은 transaction에
생성한다. active 일반 사용자와 active admin만 다른 active 사용자에게 송금할 수 있다.
송신자는 항상 현재 인증 사용자이고 수신자는 strip한 username으로 서버가 조회한다.
client가 제출한 sender ID, recipient ID, balance 또는 DB idempotency key는 사용하지 않는다.
자기 송금과 dormant·없는 사용자·Wallet, 1 미만 또는 1,000,000,000 초과 금액, 소수·bool,
잔액 초과를 거부하며 현재 비밀번호를 strip하지 않고 다시 확인한다.

`GET /wallet/transfer`는 `secrets.token_urlsafe(32)`의 43자 URL-safe token을 hidden
input으로만 전달한다. DB에는 raw token 대신 다음 sender-bound SHA-256 key만 저장한다.

```text
sha256(sender_user_id + ":" + raw_token).hexdigest()
```

raw token은 송금 form의 hidden input 외 visible text·flash·로그·감사 로그에 노출하지 않고,
derived key도 화면·DTO·감사 로그에 표시하지 않는다. 같은 key와 같은 recipient/amount는
기존 Transfer를 반환하며 차감·증가·원장·감사를 반복하지 않는다. 다른 payload 재사용은
conflict다.

신규 송금은 다음을 하나의 DB transaction으로 처리한다.

1. Transfer row를 추가하고 flush해 idempotency key를 예약한다.
2. `UPDATE wallets ... WHERE user_id = sender_id AND balance >= amount` 조건부 debit의
   `rowcount == 1`을 확인한다.
3. active recipient Wallet을 조건부 credit하고 `rowcount == 1`을 확인한다.
4. `transfer.created` AuditLog에 `amount`만 기록한다.
5. 모든 단계가 성공한 뒤 한 번만 commit한다.

commit 전 credit·audit·DB 오류는 잔액, Transfer와 AuditLog를 전부 rollback한다. commit을
실행한 뒤 예외가 발생하면 반영 여부를 단정할 수 없으므로 `DATABASE_ERROR` 응답의 유효한
원 token을 hidden input에 유지한다. 사용자는 같은 token과 payload로 재시도하고, 이미
반영됐다면 기존 Transfer를 `IDEMPOTENT`로 확인한다. 다른 payload는 conflict다. file-based
SQLite의 독립 thread/session concurrency 테스트는 잔액 100에서 80+80 과다 인출과 같은
token 동시 재전송을 검증하며 Wallet 총합을 확인한다.

완료된 Transfer를 수정·삭제하는 사용자 또는 관리자 HTTP route는 없다. 사용자 이력은
participant 조건과 fixed 20 SQL pagination, sender/recipient alias projection,
`created_at, id` 안정 정렬을 사용한다. 상세는 sender 또는 recipient 조건을 같은 query에
넣어 제3자와 없는 ID를 동일한 404로 처리한다. Wallet template에는 frozen/slots DTO만
전달하며 ORM Wallet, 내부 user ID, password hash와 idempotency key를 전달하지 않는다.

모든 Wallet 응답은 `Cache-Control: no-store, private`이다. Wallet GET은 IP당 60/minute,
송금 POST는 인증 사용자당 3/minute와 10/hour이고 CSRF를 요구한다. 성공과 동일 요청 재시도는
Transfer 상세로 303 redirect한다.

## 주요 HTTP route

| Method | 경로 | 접근·기능 |
|---|---|---|
| GET | `/products` | 공개 상품 검색·목록 |
| GET/POST | `/products/new` | 인증 사용자 상품 등록 |
| GET | `/chat` | 인증 사용자 전체 채팅 |
| GET | `/chat/direct` | 인증 사용자 1대1 대화 |
| GET/POST | `/reports/users/<username>/new` | 사용자 신고 |
| GET/POST | `/reports/products/<uuid>/new` | 상품 신고 |
| GET | `/wallet` | 현재 잔액과 본인 송금 이력 |
| GET | `/wallet/transfer` | 서버 생성 token을 포함한 송금 form |
| POST | `/wallet/transfer` | CSRF·현재 비밀번호가 필요한 원자 송금 |
| GET | `/wallet/transfers/<uuid>` | 송신자·수신자 전용 상세 |
| GET | `/admin` | active admin 대시보드 |
| GET | `/admin/transfers` | 실제 Transfer 읽기 전용 조회 |
| GET | `/admin/audit-logs` | allowlist 감사 로그 조회 |

관리자 user/product/report/message mutation은 기존과 같이 POST·CSRF·현재 관리자 비밀번호를
요구한다. `/admin/transfers`에는 mutation route가 없고 idempotency key와 내부 user ID를
조회·출력하지 않는다.

## 설정과 실행

시스템 Python이나 전역 환경 대신 저장소의 `.venv`만 사용한다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/bootstrap_env.py
.venv/bin/flask --app run.py db upgrade
.venv/bin/python run.py
```

실행 뒤 <http://127.0.0.1:5000>에 접속한다. 애플리케이션 실행과 migration 적용에는 Git
metadata가 필요하지 않다. 다만 전체 test suite의 migration 불변 테스트는 Phase 01~05
tag를 `git show`로 읽으므로 일반 `git clone` 또는 tag를 포함한 checkout이 필요하다.
GitHub Download ZIP에는 `.git`과 tag가 없어 해당 불변 테스트를 실행할 수 없다.

`scripts/bootstrap_env.py`는 `.env.example`의 placeholder를 새로운 무작위 Secret Key로
교체해 mode `0600`의 `.env`를 만들며 기존 파일은 덮어쓰지 않는다. Development·Production의
`SECRET_KEY`는 환경에서 제공한 32자 이상 무작위 문자열이어야 한다. `.env`, `.venv`,
`instance`, SQLite DB와 upload 파일은 Git 추적 대상이 아니다.

Phase 06 기본 설정은 `app/config.py`에 있다.

```text
TRANSFER_MIN_AMOUNT=1
TRANSFER_MAX_AMOUNT=1000000000
TRANSFER_HISTORY_PER_PAGE=20
TRANSFER_PAGE_MAX=1000
TRANSFER_IDEMPOTENCY_TOKEN_BYTES=32
```

SQLite 연결은 `foreign_keys=ON`과 `busy_timeout=5000ms`를 적용하며 WAL mode를 강제하지
않는다. Ubuntu/WSL과 GitHub Ubuntu 같은 POSIX 환경에서는 Flask instance directory를
symlink가 아닌 실제 directory로 확인한 뒤 descriptor로 `0700`, file-backed SQLite main
DB를 regular file로 확인한 뒤 가능한 `O_NOFOLLOW`·`O_CLOEXEC` descriptor로 `0600`을
적용한다. symlink·non-directory/non-regular target과 chmod 실패는 fail closed한다.
in-memory SQLite에는 file mode를 적용하지 않으며, non-POSIX에서는 이 POSIX mode 보장을
주장하지 않는다. process-wide umask는 변경하지 않는다.

## 관리자 생성

기본 admin 또는 source 내 기본 자격 증명은 없다. admin은 숨김 password·confirmation
prompt를 사용하는 CLI로만 생성한다.

```bash
.venv/bin/flask --app run.py create-admin --username ADMIN_USERNAME
```

생성 시 active admin, scrypt password hash, Wallet 100000과 `admin.account_created`
AuditLog를 하나의 transaction으로 저장한다. 관리자도 balance를 임의로 수정할 수 없다.

## Migration

1. `09357cac1cb7`: 안전한 기반 모델
2. `57c21fbc6f83`: 사용자 `auth_version`
3. `c3d57de11bfa`: 상품 constraint·index
4. `a91f4c8d2e70`: 채팅 constraint·index
5. `e5b7a2c9d4f1`: 신고·관리자·감사 metadata와 index
6. `f8c2d1e7a6b4`: `ck_transfers_amount_range`,
   `ck_transfers_idempotency_key_format`, sender/recipient history index

여섯 번째 revision만 Phase 06에서 추가했다. 기존 5개 migration은
`phase-05-moderation-admin` 태그와 byte 단위로 동일하다. downgrade는 두 history index와
새 CHECK를 제거하고 기존 `ck_transfers_amount_positive`를 복구한다.

## CI와 로컬 검증

`.github/workflows/ci.yml`은 `push`와 `pull_request`에서 `actions/checkout@v4`의
`fetch-depth: 0`, `persist-credentials: false`로 전체 history와 tag를 가져온다. checkout
직후 Phase 01~05 보존 tag를 `git show-ref`로 확인하고 하나라도 없으면 실패한다. 이어서
Python 3.12를 사용한다. workflow가 임시 무작위 `SECRET_KEY`와 runner 임시 SQLite 경로를
만들기 때문에 repository secret이나 `.env`가 필요하지 않다. pytest와 app coverage 90%
gate, Ruff check/format, Bandit, runtime/dev pip-audit, pip check, compileall, 빈 DB migration
upgrade와 drift check는 모두 필수 단계이며 `continue-on-error`를 사용하지 않는다.

로컬 최종 검증 명령:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/bandit -q -r app scripts run.py
PIP_NO_CACHE_DIR=1 .venv/bin/pip-audit -r requirements.txt
PIP_NO_CACHE_DIR=1 .venv/bin/pip-audit -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -m compileall -q app scripts tests run.py
git diff --check
```

Phase 06 최종 로컬 자동 테스트는 기존 518개 회귀를 유지한 총 596개다. 전체 pytest와
coverage 실행에서 모두 통과했고 현재 `app` coverage는 95%(`95.26%`)로 90% gate를
통과했다. coverage는 현재 `app` 코드 범위다. 실제 GitHub Actions runner 성공 화면은
사람이 push/PR 뒤 확인·캡처한다.

## 구조

```text
app/auth/                 인증 form·route·service
app/users/                사용자 조회·수정
app/products/             상품 form·route·service·안전한 image 처리
app/chat/                 HTTP·Socket route, service, registry, limiter, DTO
app/moderation/           신고 form·policy·transaction·DTO
app/admin/                RBAC·projection query·관리 mutation·DTO
app/audit/                action/details allowlist와 감사 생성
app/wallet/               송금 form·policy·route·transaction·history·DTO
app/templates/wallet/     지갑·송금 form·송금 상세
migrations/versions/      6개의 순차 Alembic revision
.github/workflows/ci.yml  Python 3.12 필수 CI
tests/                    HTTP·DB·rollback·idempotency·concurrency·회귀
docs/                     요구사항·설계·위협·Finding·test/evidence/manual 계획
```

## 잔여 범위와 한계

- 영구 cloud 배포, 실제 HTTPS/WSS 종료와 운영 관측은 범위 밖이며 사람이 별도 검증한다.
- Flask-Limiter memory backend와 채팅 registry는 단일 process 범위다. 다중 process 운영은
  공유 rate-limit 저장소와 Socket disconnect 전달 계층이 필요하다.
- SQLite는 높은 write concurrency에서 직렬화·lock 지연 한계가 있다. 현재 구현은
  `busy_timeout`, 짧은 transaction, 조건부 debit과 실제 file DB concurrency 테스트로
  과제 범위를 방어하지만 고처리량 운영은 별도 DB·재시도·관측 설계가 필요하다.
- AuditLog는 application DB transaction과 원자적이지만 외부 append-only/WORM 감사 저장소는
  아니다.
- 실제 브라우저 사용성·화면 캡처·GitHub Actions 성공 확인과 유지보수 사례 확정은
  `docs/MANUAL_TEST_PLAN.md`·`docs/EVIDENCE.md`에 `NOT RUN` 계획으로 남아 있다.
  실행하지 않은 유지보수 결과는 `docs/MAINTENANCE_LOG.md`에 만들지 않았다.
