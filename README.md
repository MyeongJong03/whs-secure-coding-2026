# Secure Market

교육용 중고 거래 애플리케이션을 안전한 SDLC 절차로 재구성하는 프로젝트다. Phase 01은
애플리케이션 팩토리, 보안 설정, 데이터 모델, 마이그레이션, 문서와 자동 테스트 기반만
제공한다.

## 기준선

- 강사 스타터 코드 출처: `https://github.com/ugonfor/secure-coding`
- 기준 커밋: `f0dd4baac057f62315bb4850f05d18b7e60eb4be`
- 보존 태그: `course-starter-f0dd4ba`
- Phase 01에서 기존 단일 파일 Flask 구현을 팩토리 구조로 교체했다.

## 현재 구현 상태

구현됨: 공개 index, `/health`, 공통 레이아웃, 안전한 오류 페이지, 보안 헤더,
확장 초기화, SQLAlchemy 모델, 최초 Alembic 마이그레이션, 테스트와 SDLC 문서.

미구현: 회원가입, 로그인, 로그아웃, 프로필, 상품 CRUD, 파일 업로드, 전체/1대1 채팅,
신고 처리, 송금, 관리자 UI와 Socket.IO 이벤트. 이 기능들은 다음 단계에서 인증·권한·검증
테스트를 포함한 수직 단위로 구현한다.

## 기술 스택

Python 3.12, Flask/Jinja2, Flask-SQLAlchemy, Flask-Migrate/Alembic, Flask-Login,
Flask-WTF, Flask-SocketIO, Flask-Limiter, SQLite, Werkzeug scrypt, Pillow, pytest,
Ruff, Bandit, pip-audit를 사용한다. 프런트엔드 자산은 저장소 내부에서만 제공하며 외부
CDN을 사용하지 않는다.

## 사전 요구사항과 설치

Python 3.12가 필요하다. 시스템 및 전역 환경 대신 저장소 로컬 가상환경만 사용한다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

`.env.example`을 `.env`로 복사하고 `SECRET_KEY`를 32자 이상의 무작위 값으로 반드시
바꾼다. 예제 placeholder를 그대로 둔 상태에서는 애플리케이션이 시작되지 않는다. `.env`는
Git에서 제외된다.

```bash
cp .env.example .env
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))"
```

출력값을 로컬 `.env`의 `SECRET_KEY`에 직접 넣는다. Development와 Production은 키가
누락·비문자열·빈 값·짧은 값이거나 알려진 placeholder이면 모두 시작을 거부한다. 실제 Secret
Key는 source, 문서, 테스트 fixture와 Git 추적 파일에 넣지 않는다.

## 데이터베이스 마이그레이션

```bash
.venv/bin/flask --app run.py db upgrade
```

기본 SQLite 파일은 `instance/market.db`이며 Git에서 제외된다. 현재 최초 migration은 아직
배포되지 않았으므로 Phase 01 검토 수정은 모델과 그 최초 migration을 직접 일치시키며 별도
두 번째 migration을 만들지 않는다. 이후 배포된 스키마를 변경할 때만 새 migration을 검토한다.

## 실행

```bash
.venv/bin/python run.py
```

디버그 여부는 `.env`의 `FLASK_DEBUG` 설정을 따르며 소스에 강제되지 않는다. 운영에서는
`FLASK_CONFIG=production`, 강한 `SECRET_KEY`, HTTPS와 외부 rate-limit 저장소를 별도로
구성해야 한다.

## 품질 및 보안 검사

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pytest --cov=app --cov-report=term-missing
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/bandit -q -r app run.py
PIP_NO_CACHE_DIR=1 .venv/bin/pip-audit -r requirements.txt
PIP_NO_CACHE_DIR=1 .venv/bin/pip-audit -r requirements-dev.txt
.venv/bin/python -m compileall -q app tests run.py
.venv/bin/python -m pip check
git diff --check
git status --short
```

pytest는 외부 네트워크에 의존하지 않는다. Phase 01에서 기록하는 99% coverage는 현재
`app` foundation 코드만 대상으로 하며, 아직 구현하지 않은 전체 과제 기능의 coverage가 아니다.

## 프로젝트 구조

```text
app/                 application factory, extensions, models, routes, templates, static
migrations/          Alembic migration history
tests/               application and database constraint tests
docs/                requirements, design, threat model, findings, evidence and logs
.env.example          non-secret environment template
requirements*.txt     pinned runtime/development dependencies
run.py                local entry point
```

## 보안 설계 원칙

- 서버측 인증·객체 권한·입력 검증을 신뢰 기준으로 삼는다.
- 모든 상태 변경에 CSRF를 적용하고 동적 SQL 문자열 결합을 금지한다.
- 비밀번호는 Werkzeug 기본 scrypt로만 해시하며 원문 필드를 두지 않는다.
- SQLite의 FOREIGN KEY, CHECK, UNIQUE, NOT NULL 제약으로 애플리케이션 검증을 보완한다.
- 오류 응답은 내부 예외를 숨기고 공통 보안 헤더와 제한적인 CSP를 적용한다.
- 업로드, 신고, 송금, 채팅과 관리자 기능은 서비스 계층 정책과 테스트가 준비된 단계에서만
  공개한다.

## 라이선스와 출처

이 저장소 이력은 위 강사 스타터 저장소에서 가져온 코드를 포함한다. 현재 저장소에는 별도
`LICENSE` 파일이 확인되지 않으므로, 명시되지 않은 라이선스 권리를 추정하지 않는다.
