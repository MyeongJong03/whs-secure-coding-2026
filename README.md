# Secure Market

교육용 중고 거래 애플리케이션을 안전한 SDLC 절차로 재구성하는 프로젝트다. Phase 01 기반은
`phase-01-foundation` 태그로 보존되어 있으며, 현재 Phase 02는 인증과 사용자 관리 수직 기능을
구현한다. 전체 과제는 아직 완료되지 않았다.

## 기준선

- 강사 스타터 코드: `https://github.com/ugonfor/secure-coding`
- 기준 커밋: `f0dd4baac057f62315bb4850f05d18b7e60eb4be`
- 강사 코드 보존 태그: `course-starter-f0dd4ba`
- Phase 01 보존 태그: `phase-01-foundation`

## 현재 구현 상태

Phase 02에서 구현한 기능:

- 사용자명·비밀번호 회원가입과 Werkzeug 기본 scrypt 해시
- active 사용자 로그인, POST 전용 CSRF 로그아웃, IP·사용자 단위 rate limit
- 사용자 검색·페이지네이션과 공개 프로필
- 본인 마이페이지, 소개글 변경, 현재 비밀번호 확인 후 비밀번호 변경
- `auth_version` 비교를 통한 dormant·비밀번호 변경 전 세션 무효화
- 회원가입 User와 Wallet의 단일 transaction, 초기 가상 포인트 100000
- 공개 사용자 `username`, `bio` 전용 DB projection·view model, Jinja autoescape, 인증 화면과 마이페이지의 `no-store, private`

아직 구현하지 않은 기능:

- Phase 03: 상품 CRUD, 안전한 이미지 업로드, 상품 검색
- Phase 04: 전체 및 1대1 채팅
- Phase 05: 신고, 자동 제재, 관리자 기능
- Phase 06: 가상 포인트 송금, 최종 통합 및 보안 강화

가상 포인트는 과제용 정수 값이며 실제 금융 자산이나 결제 수단이 아니다.

## 기술 스택

Python 3.12, Flask/Jinja2, Flask-SQLAlchemy, Flask-Migrate/Alembic, Flask-Login,
Flask-WTF, Flask-SocketIO, Flask-Limiter, SQLite, Werkzeug scrypt, pytest, Ruff,
Bandit, pip-audit를 사용한다. 외부 CDN 없이 저장소 내부 정적 자산만 제공한다.

## 설치와 설정

시스템·전역 환경 대신 저장소의 `.venv`만 사용한다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

`.env.example`을 `.env`로 복사한 뒤 `SECRET_KEY`를 32자 이상의 무작위 값으로 바꾼다.
placeholder, 짧은 키, 누락된 키로 Development·Production 앱을 시작할 수 없다. `.env`와 실제
Secret Key는 Git에 포함하지 않는다.

```bash
cp .env.example .env
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## migration과 실행

Phase 01 최초 revision은 `09357cac1cb7`, Phase 02의 독립된 두 번째 revision은
`57c21fbc6f83`이다. 두 번째 migration은 `users.auth_version`과 양수 CHECK 제약을 추가한다.

```bash
.venv/bin/flask --app run.py db upgrade
.venv/bin/flask --app run.py db current
.venv/bin/flask --app run.py db check
.venv/bin/python run.py
```

기본 SQLite 파일은 `instance/market.db`이며 Git에서 제외된다. 운영에서는
`FLASK_CONFIG=production`, 강한 환경 Secret Key, HTTPS와 공유 rate-limit 저장소를 별도로
구성해야 한다.

## 주요 route

| Method | 경로 | 기능 |
|---|---|---|
| GET/POST | `/auth/register` | 회원가입 |
| GET/POST | `/auth/login` | 로그인 |
| POST | `/auth/logout` | CSRF 보호 로그아웃 |
| GET | `/users` | active 사용자 검색·목록 |
| GET | `/users/<username>` | active 사용자의 공개 프로필 |
| GET | `/me` | 본인 정보·가상 포인트 |
| POST | `/me/bio` | 본인 소개글 변경 |
| POST | `/me/password` | 재인증 후 비밀번호 변경 |

## 품질 및 보안 검사

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pytest --cov=app --cov-report=term-missing
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/bandit -q -r app run.py
PIP_NO_CACHE_DIR=1 .venv/bin/pip-audit -r requirements.txt
PIP_NO_CACHE_DIR=1 .venv/bin/pip-audit -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -m compileall -q app tests run.py
git diff --check
git status --short
```

pytest는 CSRF와 rate limit을 비활성화하지 않으며 외부 네트워크에 의존하지 않는다. coverage는
현재 `app` 코드 범위이며 아직 구현하지 않은 전체 과제 기능의 완성도를 뜻하지 않는다.

## 보안 설계 원칙

- 서버측 인증·객체 권한·입력 검증을 신뢰 기준으로 삼는다.
- 모든 상태 변경에 CSRF를 적용하고 ORM과 파라미터 바인딩을 사용한다.
- 비밀번호 원문, hash, 세션 값, Secret Key를 응답·로그·AuditLog에 기록하지 않는다.
- 공개 사용자 응답은 DB SELECT와 template view model 모두 `username`, `bio`만 허용한다.
- DB CHECK, UNIQUE, NOT NULL, FOREIGN KEY로 서비스 검증을 보완한다.
- 미구현 상품·채팅·신고·송금·관리자 기능은 보호 정책과 테스트가 준비된 후속 Phase에서만
  공개한다.

## 프로젝트 구조

```text
app/auth/           인증 form, route, service
app/users/          사용자 form, route, service
app/models/         SQLAlchemy 모델과 DB 제약
app/templates/      Jinja 화면
app/static/         로컬 CSS
migrations/         Phase 01 및 Phase 02 Alembic 이력
tests/              foundation, 인증, 사용자, migration 테스트
docs/               요구사항, 설계, 위협, Finding, 증거 계획
```

## 라이선스와 출처

이 저장소 이력은 위 강사 스타터 저장소의 코드를 포함한다. 별도 `LICENSE` 파일이 확인되지
않으므로 명시되지 않은 라이선스 권리를 추정하지 않는다.
