# Design

## 현재 범위

Phase 04는 Phase 01~03 factory·인증·사용자·상품·이미지·검색 위에 전체·1대1 실시간
채팅을 구현한다. 신고, 자동 제재, 관리자 UI·메시지 hide와 송금 route는 공개하지 않는다.

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
| `app/products/policy.py` | 상품·검색·이미지 allowlist와 수치 정책의 단일 정의 |
| `app/products/forms.py` | 생성·수정·상태·삭제·검색 입력 경계 |
| `app/products/routes.py` | 인증, CSRF, rate limit, 응답과 303/404/409 흐름 |
| `app/products/services.py` | 공개 projection/DTO, 검색 SQL, 소유권, 상태와 DB transaction |
| `app/products/images.py` | bounded read, Pillow 검증·재인코딩, 안전한 저장·읽기·삭제 |
| `app/chat/routes.py` | chat HTTP 인증·pagination·no-store·redirect |
| `app/chat/services.py` | direct 생성 race, projection DTO query, message transaction |
| `app/chat/events.py` | `/chat` connect·join·send schema와 room emit |
| `app/chat/connections.py` | per-app registry, event 인증 decorator, stale prune·disconnect |
| `app/chat/rate_limit.py` | app별 monotonic user sliding-window limiter |
| `app/chat/policy.py` | namespace·server room·UUID·message normalization·generic ack |
| `app/chat/views.py` | frozen·slots history/direct view DTO |
| `app/models/` | User·Wallet·Product와 후속 Phase foundation 모델 및 DB 제약 |
| `tests/` | 기존 회귀와 chat HTTP·DB·Socket·room·static integrity 테스트 |

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
뒤 해당 user의 기존 `/chat` socket을 모두 종료하고 현재 브라우저 session을
clear·재로그인하며 새 버전을 저장한다. 현재 브라우저는 새 Socket을 만들 수 있지만 변경 전
Socket과 다른 브라우저의 이전 HTTP session은 사용할 수 없다. 실패 시 rollback하고 password,
hash, session 값을 로그나 AuditLog에 남기지 않는다.

### 로그아웃

`POST /auth/logout`만 존재한다. `login_required`, 전역 CSRF 뒤 current user ID를 보존해
해당 `/chat` socket을 모두 종료하고 `logout_user()`, `session.clear()` 순서로 처리한 뒤
로그인 화면으로 303 redirect한다. GET은 405다.

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
| GET | `/chat` | 필요 | 해당 없음 | IP 60/minute |
| GET | `/chat/direct` | 필요 | 해당 없음 | IP 60/minute |
| POST | `/chat/direct/start` | 필요 | 필요 | 사용자 20/hour |
| GET | `/chat/direct/<uuid>` | 필요·participant | 해당 없음 | IP 60/minute |

`/`와 `/health`, 공통 400/403/404/405/409/413/429/500 handler를 유지한다.

## 오류와 응답 보안

- 예상 가능한 중복, validation, CSRF, rate limit, DB 오류에는 일반적인 한국어 화면을 쓴다.
- 500 handler는 DB session을 rollback한다.
- 응답에 SQL, constraint 이름, traceback, 절대경로, password hash, auth_version, UUID를 넣지
  않는다.
- CSP는 self script/style만 허용하고 template에는 inline script/style, 외부 CDN, `safe`,
  Markup을 사용하지 않는다.
- 공통 nosniff, frame deny, referrer, permissions, CSP header를 정상·오류 응답 모두에 적용한다.

## migration

기존 `09357cac1cb7`, `57c21fbc6f83`, `c3d57de11bfa`는 수정하지 않는다. Phase 04
`a91f4c8d2e70`은 세 번째 revision을 `down_revision`으로 사용한다. SQLite batch operation으로
`ck_chat_messages_is_hidden_boolean`을 추가하고 message conversation/visibility/time,
message sender/time, direct user1/time, direct user2/time named index를 만든다. downgrade는
이 네 index와 새 CHECK만 제거하고 table·column·body CHECK·canonical UNIQUE/CHECK·FK는
유지한다. 검증 범위는 빈 DB head upgrade/current/check, Phase 03 downgrade, head
재-upgrade와 재 check다.

## 단계 계획

- Phase 02: 인증 및 사용자 관리 — 보존·회귀 유지
- Phase 03: 상품, 안전한 이미지 업로드, 상품 검색 — 보존·회귀 유지
- Phase 04: 전체 및 1대1 채팅 — 현재 구현
- Phase 05: 신고, 자동 제재, 관리자 기능
- Phase 06: 가상 포인트 송금, 최종 통합 및 보안 강화

후속 모델이 Phase 01에 존재하더라도 해당 route·service·UI가 구현되었다는 뜻은 아니다.

## Phase 03 products Blueprint

`products` Blueprint는 공개 `/products`와 소유자 `/me/products` 경로를 함께 등록한다.
route는 HTTP·form·응답만 조정하고, 검색과 transaction은 service, byte/file trust
boundary는 image 계층이 담당한다.

| Method | 경로 | service·정책 |
|---|---|---|
| GET | `/products` | 공개 projection 검색, IP 60/minute |
| GET | `/products/<uuid>` | active/sold + active seller 상세, IP 120/minute |
| GET | `/products/<uuid>/image` | 공개 또는 로그인 소유자 접근, IP 120/minute |
| GET/POST | `/products/new` | current user seller, 이미지 필수, 사용자 10/hour |
| GET | `/me/products` | current user의 모든 상태 DTO |
| GET/POST | `/me/products/<uuid>/edit` | owner + active/sold, 사용자 30/hour |
| POST | `/me/products/<uuid>/status` | owner + active/sold allowlist, 사용자 30/hour |
| POST | `/me/products/<uuid>/delete` | owner + not deleted soft delete, 사용자 30/hour |

모든 mutation은 Flask-Login과 전역 CSRF를 거친다. URL의 UUID는 식별에만 쓰고 owner query는
항상 `Product.seller_id == current_user.id`를 포함한다. 타인과 없는 객체는 404로
동일화한다. 생성·수정 form에 `seller_id`, `status`, `image_filename`이 없고 service도
해당 client 값을 받지 않는다. `hidden/deleted` 수정은 404, 상태 복구는 409다.

## 공개 Product DTO와 최소 projection

공개 template에는 Product/User ORM 객체를 전달하지 않는다.

- `PublicProductSummary`: id, title, price, status, seller_username
- `PublicProductDetail`: id, title, description, price, status, seller_username,
  created_at
- `PublicProductPage`: immutable tuple, page/per_page/total/pages와 prev/next 상태
- `OwnerProductView`: 소유자 화면용 id/title/description/price/status/timestamps/has_image

모두 frozen·slots dataclass다. 공개 SELECT projection은 URL용 Product.id, 상품 표시 필드와
User.username만 포함한다. Product.seller_id와 User.status는 JOIN/WHERE 조건에만 사용한다.
Product.image_filename, User id/hash/role/status/version, Wallet과 session은 SELECT
projection과 공개 DTO/template context에 들어가지 않는다. Jinja autoescape를 유지하고
description 줄바꿈은 CSS `white-space`로 표현한다.

## 검색 query

검색 form은 q를 strip 후 100자로 제한하고 status `all/active/sold`, 가격
1~1,000,000,000, sort `newest/oldest/price_low/price_high/title`, page 1~1000만
허용한다. `per_page` field는 없고 service는 항상 20을 사용한다.

q 조건은 title/description의 SQLAlchemy `contains(..., autoescape=True)` OR라 `%`, `_`가
literal이다. 공개 status와 active seller 조건은 모든 query에 고정된다. count query와
projection page query를 분리하고 SQL LIMIT/OFFSET을 적용한다. 정렬은 완성된 SQLAlchemy
expression tuple dictionary에서 선택하며 client column/direction 문자열을 SQL에 넣지 않는다.
모든 정렬에 id 보조 순서를 두고 pagination URL은 현재 filter를 유지한다.

## 이미지 trust boundary

`images.py`의 입력 절차:

1. 원본 filename의 `/`, `\`, NUL과 입력 확장자 allowlist를 검사한다.
2. stream은 설정된 최대 byte + 1까지만 읽고 0 byte·초과를 거부한다.
3. Pillow open에서 `DecompressionBombWarning`을 오류로 바꾸고 실제 format을 확인한다.
4. single frame 확인, `verify()`, 새 `BytesIO` 재-open을 수행한다.
5. 각 변 1~4096px, 총 16,000,000 pixel, format/extension 일치를 검사한다.
6. EXIF 방향을 적용한 뒤 JPEG는 RGB, PNG/WebP는 RGB 또는 RGBA로 변환한다.
7. image `info`를 제거하고 원본 EXIF/comment/ICC/text/trailing payload 없이 새로 encode한다.
8. encode 결과도 4 MiB 이하인지 확인한다.
9. 검증한 upload root directory descriptor에 대해 `secrets.token_hex(16)` +
   `.jpg/.png/.webp` 상대 이름을 `O_EXCL`로 만들고 file descriptor에 `fchmod(0600)`을
   적용한 뒤 write·flush·fsync한다.

upload root는 기본 `instance/uploads/products`, mode 0700이다. public web root와 template
root에 파일을 두지 않는다. `Path.resolve()` 뒤 `O_NOFOLLOW`를 적용하면 configured root
symlink를 이미 따라간 뒤라 최종 component를 방어하지 못한다. 따라서 create/read/remove
filesystem 경로에서는 `resolve()`를 사용하지 않는다. root가 없을 때만 parent와 함께 만든
뒤 최종 component를 `lstat`으로 검사하고, directory가 아니거나 symlink면 거부한다. 이어
`O_RDONLY | O_DIRECTORY`와 플랫폼이 제공하는 `O_NOFOLLOW | O_CLOEXEC`로 root를 직접 연다.
open 전 `lstat`과 open 후 `fstat`의 `st_dev`·`st_ino`가 같고 descriptor가 directory인지
확인한다. 저장 경로만 이 검증된 descriptor에 `fchmod(0700)`을 적용하므로 외부 symlink
target의 mode를 바꾸지 않는다.

생성·읽기·삭제는 모두 열린 root descriptor와 exact relative filename만 사용한다. 파일도
relative `stat(..., follow_symlinks=False)`와 가능한 `O_NOFOLLOW` open 뒤 `fstat`의
regular-file·inode identity를 확인한다. 전체 `root/filename` 절대경로를 다시 열거나 사용자
입력·DB 값으로 절대경로를 구성하지 않는다. 원본 filename은 DB, AuditLog, 로그, 응답에
저장하지 않는다.

읽기는 `^[0-9a-f]{32}\.(jpg|png|webp)$`를 먼저 검사한다. root directory descriptor와
filename relative `os.open`, 가능한 `O_NOFOLLOW`, `fstat` regular-file·size 검사, bounded
read와 실제 Pillow format/extension 일치를 거친다. 디스크 파일이 저장 뒤 바뀌어도 현재
`PRODUCT_MAX_DIMENSION`과 `PRODUCT_MAX_PIXELS`의 양수·각 변·총 pixel 제한, allowed format,
single frame, decompression warning-as-error와 `verify()`를 다시 적용한다. unsafe DB filename,
root/file symlink, missing, 손상·limit 초과 파일은 모두 404다. 공개 이미지는 5분 public
cache, 소유자 전용 비공개 이미지는 `no-store, private`; Content-Disposition은
`product.<ext>`라 원본명이나 저장명이 없다.

## filesystem과 DB coordination

생성은 이미지 검증·저장 후 Product를 한 번 commit한다. commit 실패 시 rollback하고 방금
저장한 파일을 제거한다. 교체는 새 파일을 먼저 저장한 뒤 상품 필드와 새 filename을 같은
commit에 반영한다. 실패하면 새 파일만 제거하고 이전 파일은 유지한다. 성공 후에만 이전
파일을 제거하며 제거 실패는 일반 warning만 기록하고 성공한 DB transaction을 되돌리지
않는다. soft delete는 DB status만 변경하며 row와 image를 보존한다.

파일시스템과 SQLite는 하나의 원자 transaction을 공유하지 않는다. commit과 cleanup 사이의
프로세스 crash는 고아 새 파일을 만들 수 있다. 현재 Phase에서는 존재하는 DB filename과
upload root를 비교하는 별도 보수 명령을 만들지 않았고, 후속 유지보수에서 dry-run·age
threshold·symlink 방어를 갖춘 정리 절차가 필요하다. 이는 잔여 위험이며 실제 유지보수
사건으로 기록하지 않는다.

## Phase 04 chat HTTP와 Socket 경계

`chat` Blueprint는 history와 대화 생성만 HTTP로 제공한다. message 전송과 room join은
`/chat` Socket.IO namespace event만 사용한다. GET message 전송이나 GET conversation 생성
route는 없다. HTTP `login_required`는 route에만 적용하고 Socket handler는 전용 decorator를
사용한다.

- `/chat`: global `conversation_id IS NULL`, `is_hidden=False` 최근 50개
- `/chat/direct`: 현재 user가 user1/user2인 conversation 최근 20개
- `/chat/direct/start`: username 하나만 받아 active target을 서버 조회
- `/chat/direct/<uuid>`: participant query가 성공한 경우만 해당 direct history 50개

page는 1~1000이며 최신순 SQL `LIMIT/OFFSET` 결과만 읽은 뒤 현재 page 안에서 시간순으로
뒤집어 표시한다. `created_at, id`가 안정 순서를 제공한다. page 1만 live flag가 true다.
모든 chat HTTP 응답은 `no-store, private`이고 GET은 IP 60/minute, start는 사용자
20/hour다.

## DirectConversation 생성과 권한

현재 user는 `current_user`에서만 얻고 target은 form username으로 active User를 조회한다.
현재 user 또는 target이 dormant이거나 자기 자신이면 생성하지 않는다. 두 UUID를 정렬해
항상 `user1_id < user2_id`로 만들고 기존 pair를 먼저 재사용한다. 신규 insert의 UNIQUE race는
`IntegrityError` rollback 뒤 canonical pair를 다시 조회하며 다른 DB 오류는 일반 실패로
rollback한다.

route와 event는 conversation UUID만으로 권한을 추론하지 않는다. user1/user2 participant
조건과 counterpart join을 매 요청 수행한다. 없는 conversation과 제3자의 conversation은
HTTP에서 같은 404, Socket에서 같은 `not_found`다. client room name은 받지 않으며 서버만
`chat:global`, `chat:direct:<canonical UUID>`를 생성한다.

## Connect CSRF와 event 인증

history page가 Flask-WTF `generate_csrf()`로 만든 token을 data attribute에 제공하고
`chat.js`가 `io("/chat", {auth: {csrf_token: token}})`로 연결한다. connect handler는 auth
object의 key가 `csrf_token` 하나인지, 값이 string인지, `validate_csrf()`를 통과하는지
확인한다. Engine.IO는 wildcard/빈 CORS 목록이 아닌 same-origin 기본값을 사용한다.
Socket server는 threading, synchronous handlers, `always_connect=False`, 8192-byte packet
buffer, client monitor, logger off, 별도 Engine.IO cookie 없음으로 초기화한다.

CSRF 뒤 HTTP session user ID/version, DB User active/version, `current_user` identity를 모두
확인하고 per-app registry에만 record를 넣는다. Flask session에는 값을 쓰지 않는다. 각
inbound event의 custom decorator는 다음을 다시 확인한다.

1. stale snapshot prune 뒤 현재 sid record가 존재한다.
2. session user/version과 record snapshot이 일치한다.
3. DB User가 존재하고 active이며 auth version이 record와 일치한다.
4. `current_user`가 authenticated이고 record user와 같다.
5. connection age가 `CHAT_SOCKET_MAX_AGE_SECONDS` 이하다.

실패하면 allowlisted `unauthorized`만 반환하고 record 제거와 disconnect를 수행한다. event
exception handler는 client에 `server_error`만 emit하고 server에는 allowlisted event 이름만
warning으로 남긴다. args, body, CSRF, session, sid, username은 기록하지 않는다.

## Connection registry와 stale broadcast

`ConnectionRegistry`는 app extension으로 생성되어 test/app 사이 module global 상태를
공유하지 않는다. frozen `ConnectionRecord`는 sid, user ID, auth version snapshot과 monotonic
연결 시각을 server memory에만 보유한다. RLock 아래 sid→record와 user→sid set을 함께
관리하며 기본 사용자 cap은 5다.

모든 inbound event와 room broadcast 전에 registry snapshot의 user ID를 한 번의 batch
projection query로 조회한다. missing, dormant, version mismatch, 1800초 초과 record를 먼저
registry와 Socket server에서 제거한다. `disconnect_user_sockets(user_id)`는 HTTP logout과
password 변경에서 즉시 사용하고 Phase 05 dormant 처리에서도 재사용할 수 있지만 이번
Phase에는 관리자 상태 변경 기능을 구현하지 않는다.

## Room event와 message transaction

join event는 사용자 join quota 뒤 exact schema와 direct participant를 검사한다. send event는
malformed 요청도 사용자 message quota를 먼저 소비하고 exact schema, canonical UUID,
server room membership, participant와 counterpart active를 확인한다. global/direct message
quota는 사용자 ID로 합산되어 여러 sid로 우회할 수 없다.

message body는 CRLF/CR을 LF로 바꾸고 NFC 정규화·strip한다. 1~500 Unicode code point,
UTF-8 1~2000 bytes만 허용하고 NUL·DEL 및 tab/newline 이외 C0 control을 거부한다. HTML
문자열을 sanitizer로 변형하지 않는다.

sender ID는 registry의 인증 user snapshot에서만 가져오고 created time과
`is_hidden=False`는 서버가 설정한다. global은 conversation NULL, direct는 매 event 권한
검사한 ID다. 한 번의 commit이 성공한 뒤 stale prune을 다시 수행하고 해당 server room에만
`chat:message`를 emit한다. commit 실패는 rollback하고 어떤 room에도 emit하지 않는다.

outbound allowlist는 scope, direct일 때 conversation ID, 그리고 message의 id,
sender_username, body, created_at ISO뿐이다. sender/user participant ID, role/status/version,
sid, room과 session은 포함하지 않는다.

## Chat DTO projection

template에는 ChatMessage, User, DirectConversation ORM 객체를 전달하지 않는다.

- `ChatMessageView/Page`: message id, sender username, body, created ISO와 pagination
- `DirectConversationSummary/Page`: conversation id, counterpart username, active boolean,
  created ISO와 pagination
- `DirectConversationView`: conversation id, counterpart username, active boolean

모두 frozen·slots dataclass다. SELECT projection은 표시 필드와 URL용 ID만 포함한다.
sender/conversation/participant/User ID와 User status는 JOIN/WHERE에만 쓰고 상대 사용 가능
여부는 boolean expression으로만 projection한다. password hash, role, raw status,
auth_version, Wallet, session과 sid는 DTO나 outbound payload에 없다.

## Browser client와 local supply chain

Socket.IO 4.8.3 minified 공식 bundle을 한 번 내려받아 SHA-384
`kzavj5fiMwLKzzD1f8S7TeoVIEi7uKHvbTA3ueZkrzYq75pNQUiUi6Dy98Q3fxb0`를 확인한 byte 그대로
`app/static/vendor`에 저장했다. MIT banner를 유지하고 local URL에 동일 SRI를 적용한다.
runtime template은 외부 CDN을 사용하지 않으며 CSP의 `script-src 'self'`를 바꾸지 않는다.

`chat.js`는 page data의 mode, conversation ID, connect CSRF, live flag만 읽는다. reconnect
때 server join을 다시 요청하고 client username/sender/room을 보내지 않는다. 신규 DOM은
`createElement`와 `textContent`로 만들며 `innerHTML`, `insertAdjacentHTML`, eval, inline
script/style이 없다. message ID 중복을 제거하고 live node는 200개로 제한한다.

## Custom limiter와 단일-process 잔여 위험

`ChatEventLimiter`는 app별 RLock과 monotonic timestamp deque를 사용한다. 기본 message는
global/direct 합산 5/10초와 120/hour, join은 30/60초다. 오래된 timestamp는 consume 때
제거하며 테스트 clock과 낮은 limit을 주입할 수 있다.

현재 connection registry, Socket room membership과 event limiter는 한 process memory다.
다중 worker에서는 사용자 cap, quota와 즉시 disconnect가 worker 사이에 공유되지 않는다.
운영 확장 전에 shared rate store, cross-process presence/version invalidation과 Socket.IO
message queue를 설계해야 한다. 이 잔여 위험 때문에 Phase 04를 전체 과제 완료로 표현하지
않는다.
