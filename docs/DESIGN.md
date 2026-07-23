# Design

## 현재 범위

Phase 02는 Phase 01 factory·보안 설정·foundation 모델 위에 인증과 사용자 관리만 구현한다.
상품, 이미지 업로드, 상품 검색, 전체·1대1 채팅, 신고, 송금과 관리자 UI route는 공개하지
않는다.

## 구조와 책임

```text
HTTP request
  -> Flask-WTF CSRF / WTForms 입력 검증 / Flask-Limiter
  -> auth 또는 users route: 인증·응답·redirect
  -> service: 자격 증명 판단·업무 규칙·transaction
  -> SQLAlchemy model + SQLite CHECK/UNIQUE/FK
  -> Jinja autoescape 응답
```

| 경로 | 책임 |
|---|---|
| `app/__init__.py` | factory, Blueprint 등록, version-aware user loader, 공통 header·오류 처리 |
| `app/extensions.py` | Flask-Login strong protection, DB/CSRF/Limiter 등 확장 |
| `app/security.py` | 인증 키 제거, 세션 수립·회전, private no-store, 사용자 rate-limit key |
| `app/auth/forms.py` | 가입·로그인·로그아웃 form 입력 정책 |
| `app/auth/routes.py` | 인증 HTTP 흐름, CSRF, rate limit, generic 오류, redirect |
| `app/auth/services.py` | 가입 transaction, 중복·race 처리, dummy hash 로그인 검증 |
| `app/users/forms.py` | 검색, 소개글, 비밀번호 변경 입력 정책 |
| `app/users/routes.py` | 공개 사용자 조회와 현재 사용자 전용 route |
| `app/users/services.py` | 공개 column projection·view model, 소개글 commit, 비밀번호 hash·버전 transaction |
| `app/models/` | User·Wallet과 후속 Phase foundation 모델 및 DB 제약 |
| `tests/` | foundation, 인증, 사용자, migration, 실패 분기 회귀 테스트 |

## User와 Wallet

User는 UUID PK, unique `username`, scrypt `password_hash`, `bio`, `role`, `status`,
`auth_version`, 생성·변경 시각을 가진다. `auth_version`은 integer, NOT NULL, Python·server
default 1이며 `ck_users_auth_version_positive`가 1 이상을 강제한다. 비밀번호 원문 컬럼은 없다.

Wallet은 User와 PK/FK 1:1이고 기본 balance는 100000이며 음수를 DB CHECK로 거부한다. Phase
02는 가입 시 명시적으로 100000을 설정한다. 이 포인트는 실제 금융 자산이 아니다.

## 인증 세션

Flask-Login 설정은 다음과 같다.

- `login_view = "auth.login"`
- `session_protection = "strong"`
- remember-me 미제공
- 성공 세션은 permanent이며 기존 lifetime은 8시간
- Development·Testing cookie는 HttpOnly, SameSite=Lax이고 Production은 Secure도 사용

### 로그인과 세션 생성

1. WTForms가 trim된 username과 strip하지 않은 password를 검증한다.
2. service가 정확한 username을 ORM으로 조회한다.
3. active 사용자만 실제 hash를 검사한다. 존재하지 않거나 dormant이면 앱 시작 시 무작위
   입력으로 만든 dummy scrypt hash를 검사한다.
4. 실패는 모두 HTTP 401, 같은 일반 메시지와 같은 로그인 화면 구조를 반환한다.
5. 성공하면 `session.clear()` 후 `login_user(..., remember=False, fresh=True)`를 호출한다.
6. DB의 `auth_version`을 세션에 저장하고 `session.permanent=True`로 설정한다.
7. `/me`로 303 redirect한다. `next`와 외부 URL은 읽지 않는다.

로그인 POST에는 IP당 5회/minute와 20회/hour 제한을 함께 적용한다. GET에는 이 제한을
적용하지 않으며 영구 계정 잠금은 없다.

### 매 요청 검증과 무효화

user loader는 user 존재, `status == active`, 세션 버전 존재, 세션·DB 버전의 타입까지 포함한
정확한 일치를 모두 요구한다. 하나라도 실패하면 User를 반환하지 않고 다음 키만 제거한다.

```text
_user_id, _fresh, _id, _remember, auth_version
```

전체 session을 지우지 않는다. 인증 키가 제거되므로 dormant 사용자가 다음 요청에서
anonymous가 된 뒤 active로 복구되어도 과거 cookie는 인증 상태로 부활하지 않는다.

### 비밀번호 변경

현재 비밀번호, 새 비밀번호와 확인 필드 각각의 12~128자, 확인 일치, 현재와 다른 값을 모두
확인한다. 성공 시 새 scrypt hash와 `auth_version + 1`을 같은 transaction으로 commit한다. 그
뒤 현재 User 객체를 확정해 두고 현재 브라우저 session을 clear·재로그인하며 새 버전을
저장한다. 현재 브라우저는 로그인을 유지하지만 다른 브라우저의 이전 버전 session은 다음
요청에서 제거된다. 실패 시 rollback하고 password, hash, session 값을 로그나 AuditLog에
남기지 않는다.

### 로그아웃

`POST /auth/logout`만 존재한다. `login_required`, 전역 CSRF, `logout_user()`, `session.clear()`
순서로 처리하고 로그인 화면으로 303 redirect한다. GET은 405다.

## 회원가입 transaction

입력 필드는 username, password, password confirmation뿐이다. role, status, auth_version,
balance를 form이나 service 인자로 받지 않으므로 임의 POST 필드는 무시된다.

1. username을 trim하고 ASCII 영문 대·소문자, 숫자, 밑줄 4~32자를 검사한다.
2. password와 confirmation은 strip하지 않고 각각 12~128자와 일치를 검사한다.
3. username 중복을 미리 조회한다.
4. User를 `role=user`, `status=active`, `auth_version=1`로 만들고 `set_password()`를 호출한다.
5. 같은 unit of work에 Wallet balance 100000을 추가한다.
6. 한 번만 commit한다.
7. DB UNIQUE race의 `IntegrityError`와 기타 DB 오류는 반드시 rollback하며 일반 오류만
   노출한다.
8. 성공해도 자동 로그인하지 않고 `/auth/login`으로 303 redirect한다.

가입 POST는 IP당 5회/hour로 제한한다.

## 사용자 조회와 공개 정보

공개 allowlist는 `username`, `bio` 두 필드뿐이다. 공개 SELECT 절도 이 두 column만
projection하며 전체 User ORM 객체를 공개 template context에 전달하지 않는다. password hash,
내부 UUID, role, status, auth_version, Wallet balance, timestamp와 session 정보는 공개 조회
결과나 template context에 포함하지 않는다.

service 경계의 immutable view model은 다음과 같다.

- `PublicUserView`: frozen·slots dataclass이며 `username`, `bio`만 가진다.
- `PublicUserPage`: frozen·slots dataclass이며 `items`, `page`, `per_page`, `total`, `pages`와
  이전·다음 페이지 속성을 가진다. `items`는 `PublicUserView` tuple이다.

`GET /users`는 비회원에게 열려 있고 active 사용자만 대상으로 username substring을 ORM
조건으로 검색한다. `q`는 최대 32자, `page`는 1~1000, `per_page`는 서버 고정 20이다. client의
`per_page`는 읽지 않는다. service는 같은 active·검색 조건의 count query로 total을 구한 뒤
`SELECT users.username, users.bio` page query에 username 오름차순, id 보조 정렬, limit과
offset을 적용한다. status는 WHERE, id는 ORDER BY에서만 사용하고 SELECT projection에는
포함하지 않는다. 따라서 현재 페이지는 최대 20개만 읽으며 전체 결과를 메모리에서 자르지
않는다. 사용자 검색은 IP당 60회/minute로 제한한다.

`GET /users/<username>`도 `SELECT users.username, users.bio`로 active 사용자만 조회해
`PublicUserView`를 반환한다. 없는 사용자와 dormant 사용자는 같은 404 handler를 사용한다.

## 마이페이지와 소개글

`GET /me`는 `login_required`이며 URL/query/form에서 대상 user ID를 받지 않는다. 현재 User의
username, bio와 1:1 Wallet balance만 표시하고 실제 금융 자산이 아닌 과제용 가상 포인트임을
명시한다.

`POST /me/bio`는 현재 User만 갱신하며 빈 값부터 500자까지 허용한다. Markup·`safe`를 쓰지
않고 Jinja autoescape로 저장 XSS를 출력 시 escape한다. DB 오류는 rollback한다. 사용자당
30회/hour로 제한한다.

인증 form, 인증 오류·redirect, `/me`와 그 POST 응답은 `Cache-Control: no-store, private`를
사용한다.

## 확정 route

| Method | 경로 | 인증 | CSRF | rate limit |
|---|---|---:|---:|---|
| GET/POST | `/auth/register` | 로그인 사용자는 `/me` 이동 | POST | POST IP 5/hour |
| GET/POST | `/auth/login` | 로그인 사용자는 `/me` 이동 | POST | POST IP 5/minute, 20/hour |
| POST | `/auth/logout` | 필요 | 필요 | 없음 |
| GET | `/users` | 공개 | 해당 없음 | IP 60/minute |
| GET | `/users/<username>` | 공개 | 해당 없음 | 없음 |
| GET | `/me` | 필요 | 해당 없음 | 없음 |
| POST | `/me/bio` | 필요 | 필요 | 사용자 30/hour |
| POST | `/me/password` | 필요 | 필요 | 사용자 5/hour |

`/`와 `/health`, 공통 400/403/404/429/500 handler는 Phase 01 구현을 유지한다.

## 오류와 응답 보안

- 예상 가능한 중복, validation, CSRF, rate limit, DB 오류에는 일반적인 한국어 화면을 쓴다.
- 500 handler는 DB session을 rollback한다.
- 응답에 SQL, constraint 이름, traceback, 절대경로, password hash, auth_version, UUID를 넣지
  않는다.
- CSP는 self script/style만 허용하고 template에는 inline script/style, 외부 CDN, `safe`,
  Markup을 사용하지 않는다.
- 공통 nosniff, frame deny, referrer, permissions, CSP header를 정상·오류 응답 모두에 적용한다.

## migration

Phase 01 `09357cac1cb7`은 수정하지 않는다. Phase 02 `57c21fbc6f83`은 이를
`down_revision`으로 사용하고 SQLite batch operation으로 `auth_version`과 named CHECK를
추가한다. downgrade는 CHECK와 column을 제거한다. 검증 범위는 빈 DB head upgrade, current,
drift check, 첫 revision downgrade, head 재-upgrade, 재 drift check다.

## 단계 계획

- Phase 02: 인증 및 사용자 관리 — 현재 구현
- Phase 03: 상품, 안전한 이미지 업로드, 상품 검색
- Phase 04: 전체 및 1대1 채팅
- Phase 05: 신고, 자동 제재, 관리자 기능
- Phase 06: 가상 포인트 송금, 최종 통합 및 보안 강화

후속 모델이 Phase 01에 존재하더라도 해당 route·service·UI가 구현되었다는 뜻은 아니다.
