# Test Matrix

## 자동화 원칙

Flask-WTF CSRF는 Testing에서도 활성이다. fixture는 Flask-Limiter의 in-memory counter를 테스트
전후 reset하지만 limit 자체는 끄지 않는다. 인증 상태 관찰 route는 `tests`가 만든 fixture
application에만 등록되고 운영 source에는 없다. 테스트를 삭제·skip·약화하지 않는다.

## Phase 01 회귀

기존 48개 collected test는 factory, Secret Key, CSRF extension, index/health, 공통 header·오류,
active/dormant loader, SQLite FK, username·Wallet·Product·Report·Transfer·DirectConversation
제약과 scrypt 모델 동작을 계속 검증한다. Phase 02 session 정책에 맞게 기존 active/dormant
loader 테스트는 실제 versioned 로그인으로 세션을 만든 뒤 같은 기대 결과를 확인한다.
Phase 04 추가 전의 기존 307개 Phase 01~03 테스트는 삭제·skip·약화하지 않고 모두 유지한다.

## Phase 02 migration·모델

| 테스트 ID | 요구사항 | 정상/비정상 조건 | 예상 결과 | 자동화 결과 |
|---|---|---|---|---|
| T-MIG-02 | auth_version default | User 생성 | 값 1 | PASS |
| T-MIG-03 | auth_version CHECK | 0, -1 직접 commit | IntegrityError와 rollback | PASS |
| T-MIG-04 | migration 이력 | 두 번째 revision·down_revision·batch·named CHECK·downgrade 정적 검사 | 정책 일치 | PASS |
| T-MIG-05 | Phase 01 보존 | 현재 최초 migration과 `phase-01-foundation` tag 비교 | byte 동일 | PASS |
| T-MIG-06 | upgrade/downgrade/drift | 빈 DB head, current, check, 첫 revision downgrade, head 재-upgrade, check | 전 명령 성공·column/constraint 전이 확인 | PASS |

## 회원가입

| 테스트 ID | 정상/비정상 조건 | 예상 결과 | 자동화 결과 |
|---|---|---|---|
| T-AUTH-REG-01 | GET, CSRF 없는 POST | 200/no-store, 400 | PASS |
| T-AUTH-REG-02 | trim username·정상 password | 303 login, 비자동 로그인 | PASS |
| T-AUTH-REG-03 | 정상 가입 DB | User+Wallet 100000, role user, active, version 1 | PASS |
| T-AUTH-REG-04 | 같은 password의 두 가입 | 서로 다른 scrypt hash, 평문 없음 | PASS |
| T-AUTH-REG-05 | username 길이·문자 경계 | 비정상 400 | PASS |
| T-AUTH-REG-06 | password와 confirmation 각각 11/129, confirmation mismatch | 400, 제출 값 미반사, 부분 row 없음 | PASS |
| T-AUTH-REG-07 | 사전 중복 | 일반 400, constraint/traceback 비노출 | PASS |
| T-AUTH-REG-08 | UNIQUE race IntegrityError | rollback, duplicate 결과 | PASS |
| T-AUTH-REG-09 | 임의 role/status/version/balance | 무시하고 서버 고정 값 저장 | PASS |
| T-AUTH-REG-10 | 일반 SQLAlchemyError | User·Wallet rollback, 내부 detail 비노출 | PASS |
| T-AUTH-REG-11 | GET 반복과 POST 6회 | GET 미제한, 6번째 POST 429 | PASS |

## 로그인·로그아웃·세션

| 테스트 ID | 정상/비정상 조건 | 예상 결과 | 자동화 결과 |
|---|---|---|---|
| T-AUTH-LOGIN-01 | GET, CSRF 없는 POST | 200/no-store, 400 | PASS |
| T-AUTH-LOGIN-02 | active 정상 자격 증명 | `/me` 303, permanent, version 저장 | PASS |
| T-AUTH-LOGIN-03 | 잘못된 password·없는 user·dormant | 같은 401·일반 메시지·form 구조 | PASS |
| T-AUTH-LOGIN-04 | malformed username/password | 일반 오류, password 미반사 | PASS |
| T-AUTH-LOGIN-05 | 로그인 전 session marker | 성공 뒤 제거 | PASS |
| T-AUTH-LOGIN-06 | remember와 cookie | remember cookie 없음, HttpOnly, SameSite=Lax | PASS |
| T-AUTH-LOGIN-07 | 외부 next | 무시하고 `/me`만 redirect | PASS |
| T-AUTH-LOGIN-08 | 인증 사용자의 login/register GET | `/me` 303 | PASS |
| T-AUTH-LOGIN-09 | 실패 POST 6회 | 처음 5회 동일 401, 이후 안전한 429 | PASS |
| T-AUTH-SESSION-01 | login manager 설정 | login view와 strong protection | PASS |
| T-AUTH-SESSION-02 | active versioned session | 인증 성공 | PASS |
| T-AUTH-SESSION-03 | version 누락·값 mismatch·타입 mismatch | anonymous와 인증 키 purge | PASS |
| T-AUTH-SESSION-04 | dormant 후 active 재전환 | 과거 client는 계속 anonymous | PASS |
| T-AUTH-SESSION-05 | 삭제된 user ID | anonymous와 인증 키 purge | PASS |
| T-AUTH-SESSION-06 | Production config | cookie Secure=true | PASS |
| T-AUTH-LOGOUT-01 | GET, CSRF 없는 POST, 정상 POST | 405, 400, 303과 인증 키 제거 | PASS |

## 사용자 조회·마이페이지

| 테스트 ID | 정상/비정상 조건 | 예상 결과 | 자동화 결과 |
|---|---|---|---|
| T-USER-PUBLIC-01 | 비회원 목록·active/dormant 혼합 | active username/bio만 표시 | PASS |
| T-USER-PUBLIC-02 | substring 및 underscore 검색 | ORM literal substring 결과 | PASS |
| T-USER-PUBLIC-03 | q 33, page 0/-1/1001/non-int | 400 | PASS |
| T-USER-PUBLIC-04 | 25명과 임의 per_page | 서버 고정 20/5 pagination | PASS |
| T-USER-PUBLIC-05 | username 순서 | username, id 안정 정렬 | PASS |
| T-USER-PUBLIC-06 | 검색 61회 | 61번째 429 | PASS |
| T-USER-PUBLIC-07 | active profile | username/bio만 표시 | PASS |
| T-USER-PUBLIC-08 | dormant·없는 profile | 동일 404 | PASS |
| T-USER-PUBLIC-09 | 검색 결과 없음 | 200과 정상 빈 page | PASS |
| T-USER-PUBLIC-10 | `PublicUserView` dataclass | frozen·slots, field가 username/bio뿐이고 민감 attribute 없음 | PASS |
| T-USER-PUBLIC-11 | 목록 service 실제 실행 SQL | page SELECT는 username/bio만 projection, status WHERE와 id ORDER BY만 허용 | PASS |
| T-USER-PUBLIC-12 | profile service 실제 실행 SQL | SELECT는 username/bio만 projection, status는 WHERE에서만 사용 | PASS |
| T-USER-PUBLIC-13 | 목록·profile route template context | `PublicUserPage`·`PublicUserView`이며 User ORM 객체 없음 | PASS |
| T-USER-ME-01 | anonymous/active | redirect 또는 본인 username/bio/balance | PASS |
| T-USER-ME-02 | 마이페이지 | `no-store, private`, 가상 포인트 안내 | PASS |
| T-USER-BIO-01 | CSRF 없음, 정상, 빈 값 | 400, 303, 빈 값 저장 | PASS |
| T-USER-BIO-02 | 501자 | 400과 기존 값 보존 | PASS |
| T-USER-BIO-03 | script bio | 저장 후 me/profile에서 autoescape | PASS |
| T-USER-BIO-04 | 다른 user_id 필드 | 무시하고 현재 사용자만 변경 | PASS |
| T-USER-BIO-05 | DB 오류 | rollback, 일반 400, 내부 detail 비노출 | PASS |
| T-USER-BIO-06 | 사용자 POST 31회 | 처음 30회 허용, 31번째 429 | PASS |

## 비밀번호 변경

| 테스트 ID | 정상/비정상 조건 | 예상 결과 | 자동화 결과 |
|---|---|---|---|
| T-AUTH-PW-01 | CSRF 없음 | 400 | PASS |
| T-AUTH-PW-02 | 현재 password 오류 | 400, hash/version 유지 | PASS |
| T-AUTH-PW-03 | confirmation mismatch | 400, hash/version 유지 | PASS |
| T-AUTH-PW-04 | 새 password와 confirmation 각각 11/129자·현재와 동일 | 400, 제출 값 미반사, hash/version 유지 | PASS |
| T-AUTH-PW-05 | 정상 변경 | hash 변경, version +1, 303 | PASS |
| T-AUTH-PW-06 | 현재 client | 새 version permanent session으로 인증 유지 | PASS |
| T-AUTH-PW-07 | 두 번째 client | 다음 요청 anonymous | PASS |
| T-AUTH-PW-08 | 기존/새 자격 증명 로그인 | 기존 401, 새 값 303 | PASS |
| T-AUTH-PW-09 | DB 오류 | rollback, 내부 detail 비노출 | PASS |
| T-AUTH-PW-10 | 사용자 POST 6회 | 처음 5회 처리, 6번째 429 | PASS |

## 응답·source 보안

| 테스트 ID | 검증 | 예상 결과 | 자동화 결과 |
|---|---|---|---|
| T-SEC-01 | 인증·사용자 정상/오류 응답 | 기존 CSP/nosniff/frame header 유지 | PASS |
| T-SEC-02 | 가입·로그인·password 실패 | 제출 password 미반사 | PASS |
| T-SEC-03 | 공개 목록·profile | SQL projection·DTO allowlist와 hash/UUID/role/status/version/balance 미노출 | PASS |
| T-SEC-04 | template 정적 검사 | inline script/style, `safe`, Markup 없음 | PASS |
| T-SEC-05 | 일반 가입 권한 필드·외부 redirect | admin 획득·open redirect 불가 | PASS |
| T-SEC-06 | 중복·DB 오류·404/429/500 | constraint, traceback, 절대경로 비노출 | PASS |

## Phase 03 migration·DB

| 테스트 ID | 정상/비정상 조건 | DB/filesystem/HTTP 예상 결과 | 자동화 결과 |
|---|---|---|---|
| T-MIG-07 | 세 번째 revision chain·세 파일 수 | Phase 02 down_revision, migration 3개 | PASS |
| T-MIG-08 | 이전 두 migration과 보존 tag | byte 동일 | PASS |
| T-MIG-09 | 빈 DB head→Phase 02 downgrade→head | CHECK/UNIQUE/index 전이, drift 없음 | PASS |
| T-PRODUCT-DB-01 | price 0/-1/1,000,000,001 | DB IntegrityError·rollback | PASS |
| T-PRODUCT-DB-02 | price 1/1,000,000,000 | DB commit | PASS |
| T-PRODUCT-DB-03 | 중복 image_filename·복수 NULL | 중복 거부, legacy NULL 허용 | PASS |
| T-PRODUCT-DB-04 | inspector named schema | CHECK·UNIQUE·3 index column 일치 | PASS |

## 상품 생성·이미지

| 테스트 ID | 정상/비정상 조건 | DB/filesystem/HTTP 예상 결과 | 자동화 결과 |
|---|---|---|---|
| T-PRODUCT-CREATE-01 | 비인증/GET/CSRF 없음 | login redirect/200/400, private cache | PASS |
| T-PRODUCT-CREATE-02 | JPEG/PNG/WebP 정상 | 303, current seller, active, trim, row+0600 파일 | PASS |
| T-PRODUCT-CREATE-03 | 임의 seller/status/image_filename | 무시하고 서버 값 저장 | PASS |
| T-PRODUCT-CREATE-04 | title/description/price/image 경계 | 400, row·파일 없음 | PASS |
| T-PRODUCT-CREATE-05 | DB commit 오류 | rollback, 신규 파일 제거 | PASS |
| T-PRODUCT-CREATE-06 | 사용자 POST 11회 | 11번째 429 | PASS |
| T-IMAGE-01 | actual format·extension·mode | JPEG→jpg/RGB, PNG/WebP→RGB(A) | PASS |
| T-IMAGE-02 | empty/text/SVG/BMP/GIF/corrupt/mismatch | 일반 validation 오류, 저장 없음 | PASS |
| T-IMAGE-03 | separator/NUL/unsafe extension | 일반 validation 오류, 외부 경로 영향 없음 | PASS |
| T-IMAGE-04 | input byte/dimension/pixel/warning | bounded read, limit 초과 거부 | PASS |
| T-IMAGE-05 | animated PNG/WebP | 거부 | PASS |
| T-IMAGE-06 | EXIF/comment/ICC/PNG text | 방향 적용, metadata 제거 | PASS |
| T-IMAGE-07 | trailing script/ZIP marker | 재인코딩 결과에 marker 없음 | PASS |
| T-IMAGE-08 | random collision | O_EXCL, 기존 file byte 불변, 새 random name | PASS |
| T-IMAGE-09 | unsafe DB name/symlink/missing/oversize | read/remove 거부, HTTP 404 | PASS |
| T-IMAGE-10 | 저장 root/file mode | 0700/0600 | PASS |
| T-IMAGE-11 | 5 MiB 요청 초과 | 일반 413, 원본명·path·exception 비노출 | PASS |
| T-IMAGE-12 | configured upload root가 external directory symlink | store 일반 오류, read None/HTTP 404, remove false | PASS |
| T-IMAGE-13 | root symlink store/read/remove와 inode mismatch | target 새 파일·기존 byte·directory mode 무변경, mismatch descriptor close | PASS |
| T-IMAGE-14 | store filesystem open 추적 | random relative filename과 root dir_fd, file 0600·root 0700 | PASS |
| T-IMAGE-15 | disk의 valid JPEG/PNG/WebP가 현재 dimension 초과 | read None/HTTP 404 | PASS |
| T-IMAGE-16 | disk image가 현재 pixel 초과·animation·bomb warning | read None/HTTP 404 | PASS |
| T-IMAGE-17 | 정상 store 뒤 read | content·MIME·extension 정상 | PASS |

## 환경 bootstrap

| 테스트 ID | 정상/비정상 조건 | filesystem/CLI 예상 결과 | 자동화 결과 |
|---|---|---|---|
| T-BOOTSTRAP-01 | 기본 `.env.example`과 기본 target | placeholder 한 곳 교체, 다른 항목 보존, Secret Key 32자 이상, mode 0600 | PASS |
| T-BOOTSTRAP-02 | CLI 성공 | target path와 다음 단계만 출력, 생성 Secret Key stdout/stderr 부재 | PASS |
| T-BOOTSTRAP-03 | 기존 target·placeholder 0/2개·없는 example | nonzero/exception, 기존 bytes 불변, 새 target 없음 | PASS |
| T-BOOTSTRAP-04 | 부분 write 오류·custom tmp target | 부분 target cleanup, 저장소 실제 `.env` 무변경 | PASS |

## 공개·소유자 상품

| 테스트 ID | 정상/비정상 조건 | DB/filesystem/HTTP 예상 결과 | 자동화 결과 |
|---|---|---|---|
| T-PRODUCT-PUBLIC-01 | active/sold + active seller | 목록·상세·image 200 | PASS |
| T-PRODUCT-PUBLIC-02 | hidden/deleted/dormant seller | 공개 목록 제외, 상세·image 404 | PASS |
| T-PRODUCT-PUBLIC-03 | 없는/잘못된 UUID | 동일 404 | PASS |
| T-PRODUCT-PUBLIC-04 | 저장 XSS·민감 field | escape, username만 공개, UUID/hash/role/balance/file명 없음 | PASS |
| T-PRODUCT-PUBLIC-05 | SQL/DTO/template context | explicit projection, frozen slots DTO, ORM 객체 없음 | PASS |
| T-PRODUCT-PUBLIC-06 | image format/header/cache | 실제 MIME, nosniff, generic inline name, public cache | PASS |
| T-PRODUCT-OWNER-01 | 본인/타인과 4개 상태 | 본인 전체만 private 목록 | PASS |
| T-PRODUCT-OWNER-02 | active/sold edit와 임의 field | 허용 field만 commit, owner/status/image 유지 | PASS |
| T-PRODUCT-OWNER-03 | 이미지 교체 성공/DB 실패 | 성공 old 제거; 실패 new 제거·old 유지 | PASS |
| T-PRODUCT-OWNER-04 | 타인 edit/status/delete | 동일 404, DB 불변 | PASS |
| T-PRODUCT-OWNER-05 | active↔sold/same status | 303, allowlisted DB 상태 | PASS |
| T-PRODUCT-OWNER-06 | hidden/deleted 수정·복구 | 404/409, DB 불변 | PASS |
| T-PRODUCT-OWNER-07 | soft delete | row+file 유지, status deleted, 공개 즉시 404 | PASS |
| T-PRODUCT-OWNER-08 | owner 비공개 image/타인 | owner 200 private no-store, 타인 404 | PASS |
| T-PRODUCT-OWNER-09 | mutation CSRF/method/rate | 400/405/429 | PASS |

## 상품 검색

| 테스트 ID | 정상/비정상 조건 | DB/filesystem/HTTP 예상 결과 | 자동화 결과 |
|---|---|---|---|
| T-SEARCH-01 | title/description substring | 공개 일치 row만 200 | PASS |
| T-SEARCH-02 | `%`, `_`, SQLi 형태 | literal parameter binding, 오류·확장 매치 없음 | PASS |
| T-SEARCH-03 | all/active/sold와 hidden/deleted 요청 | 공개 allowlist만, 비공개 항상 제외 | PASS |
| T-SEARCH-04 | min/max/both/min>max | 범위 결과 또는 400 | PASS |
| T-SEARCH-05 | 다섯 sort | 완성 expression allowlist와 id 안정 정렬 | PASS |
| T-SEARCH-06 | q/status/sort/page/price invalid | 400 | PASS |
| T-SEARCH-07 | 21개·client per_page=100 | SQL LIMIT 20, page link filter 유지 | PASS |
| T-SEARCH-08 | 빈 결과 | 200 정상 empty page | PASS |
| T-SEARCH-09 | 61 GET | 61번째 429 | PASS |
| T-SEARCH-10 | service source | dynamic SQL text/정렬 문자열/unbounded all 없음 | PASS |

## Phase 04 migration·DB·static

| Test ID | 입력/행동 | 기대 결과 | 상태 |
|---|---|---|---|
| T-MIG-10 | 네 번째 revision source·파일 수 | Phase 03 down_revision, migration Python 4개, boolean CHECK·named index 4개 | PASS |
| T-MIG-11 | 기존 세 migration과 `phase-03-products-search` tag | 세 파일 byte 동일 | PASS |
| T-MIG-12 | 빈 DB head→Phase 03 downgrade→head와 두 db check | CHECK/index 전이, body CHECK·conversation FK 유지, drift 없음 | PASS |
| T-CHAT-DB-01 | raw `is_hidden=-1/2` | DB IntegrityError·rollback | PASS |
| T-CHAT-DB-02 | raw `is_hidden=0/1` | DB 저장·boolean 조회 | PASS |
| T-CHAT-DB-03 | 모델 schema introspection | boolean CHECK, message 2/direct 2 named index | PASS |
| T-CHAT-STATIC-01 | local Socket.IO bundle | 공식 banner 유지, SHA-384 exact match | PASS |
| T-CHAT-STATIC-02 | chat template·notice·requirements | local URL+SRI, MIT/공식 URL, socketio/engineio/websocket exact pin | PASS |
| T-CHAT-STATIC-03 | Socket server runtime config | threading, sync handler, 8192 buffer, same-origin, cookie 없음, `/chat` handler | PASS |
| T-CHAT-STATIC-04 | `chat.js`·template source | textContent/createElement, 외부 URL·inline·innerHTML·eval 없음 | PASS |

## Phase 04 HTTP와 DTO

| Test ID | 입력/행동 | 기대 결과 | 상태 |
|---|---|---|---|
| T-CHAT-HTTP-01 | 비인증 global/direct index/page | login redirect | PASS |
| T-CHAT-HTTP-02 | 인증 `/chat` page 1·2 | 200/private, latest 50·older 5, page 1만 live | PASS |
| T-CHAT-HTTP-03 | global/direct page 0/1001/non-int | 400 | PASS |
| T-CHAT-HTTP-04 | global/direct/hidden 혼합 history | scope 일치와 `is_hidden=False`만 표시 | PASS |
| T-CHAT-HTTP-05 | script message history | Jinja escape, executable tag 없음 | PASS |
| T-CHAT-HTTP-06 | 25 direct conversation+제3자 pair | 본인 page 20/5만 표시 | PASS |
| T-CHAT-START-01 | CSRF 없음·malformed username | 400 또는 generic 303 | PASS |
| T-CHAT-START-02 | active target 두 번 | canonical 한 row 생성 뒤 기존 재사용, 303 | PASS |
| T-CHAT-START-03 | 자기/없는/dormant/current dormant | 같은 target unavailable 흐름 | PASS |
| T-CHAT-START-04 | UNIQUE race·일반 DB 오류 | rollback 후 기존 row 또는 generic database error | PASS |
| T-CHAT-START-05 | 사용자 21회/hour | 20회 처리, 21번째 429 | PASS |
| T-CHAT-DIRECT-HTTP-01 | participant 2명·제3자·missing | participant 200, 제3자/missing 동일 404 | PASS |
| T-CHAT-DIRECT-HTTP-02 | direct scope·hidden·다른 direct/global 혼합 | 해당 direct visible message만 표시 | PASS |
| T-CHAT-DIRECT-HTTP-03 | dormant counterpart | history 200, live/send form 없음 | PASS |
| T-CHAT-DTO-01 | history/direct DTO | frozen·slots, 내부 user/sender/role/version/status field 없음 | PASS |

## Phase 04 Socket connect·global

| Test ID | 입력/행동 | 기대 결과 | 상태 |
|---|---|---|---|
| T-CHAT-CONNECT-01 | 비인증+valid CSRF | connect 거부 | PASS |
| T-CHAT-CONNECT-02 | auth 없음/빈/invalid/extra | connect 거부 | PASS |
| T-CHAT-CONNECT-03 | 다른 Flask session CSRF | connect 거부 | PASS |
| T-CHAT-CONNECT-04 | valid active session | connect·registry add, Flask session key 불변 | PASS |
| T-CHAT-CONNECT-05 | dormant/version mismatch | connect 거부 | PASS |
| T-CHAT-CONNECT-06 | 같은 user 6 sockets | 5개 허용, 6번째 거부 | PASS |
| T-CHAT-CONNECT-07 | disconnect·두 app fixture | registry 제거·app별 registry/limiter identity 분리 | PASS |
| T-CHAT-GLOBAL-01 | join 전 send·정상 join | `not_joined`, 정상 ack | PASS |
| T-CHAT-GLOBAL-02 | sender/socket receiver/nonjoined socket | server sender 저장, joined 2명만 수신 | PASS |
| T-CHAT-GLOBAL-03 | username/sender/is_hidden/extra spoof | strict schema `invalid_payload`, 저장 없음 | PASS |
| T-CHAT-GLOBAL-04 | non-dict/missing/blank/501/byte/control | `invalid_payload`, 저장·broadcast 없음 | PASS |
| T-CHAT-GLOBAL-05 | decomposed Unicode·CRLF/CR | NFC와 LF로 저장·emit | PASS |
| T-CHAT-GLOBAL-06 | 500 emoji=2000 bytes·낮춘 byte config | 경계 허용·config 초과 거부 | PASS |
| T-CHAT-GLOBAL-07 | DB commit SQLAlchemyError | rollback, `server_error`, room 미broadcast | PASS |
| T-CHAT-RATE-01 | 6 burst·두 sid 교차 | user 합산 5개 저장, 6번째 rate_limited | PASS |
| T-CHAT-RATE-02 | 낮춘 hourly·join limit과 clock | 정확한 임계치, expiry 뒤 prune·재허용 | PASS |
| T-CHAT-RATE-03 | malformed send 5회 뒤 valid | malformed도 quota 소비, valid rate_limited | PASS |

## Phase 04 direct room·stale lifecycle

| Test ID | 입력/행동 | 기대 결과 | 상태 |
|---|---|---|---|
| T-CHAT-DIRECT-01 | participant 둘·제3자 direct join | participant ack, 제3자 `not_found` | PASS |
| T-CHAT-DIRECT-02 | invalid UUID·missing key·room extra | `invalid_payload` 또는 generic `not_found` | PASS |
| T-CHAT-DIRECT-03 | join 없이 send·다른 conversation | `not_joined`, 저장 없음 | PASS |
| T-CHAT-DIRECT-04 | 정상 direct send | exact conversation 저장, 두 participant만 수신 | PASS |
| T-CHAT-DIRECT-05 | 제3자 global room | direct message 미수신 | PASS |
| T-CHAT-DIRECT-06 | sender spoof·extra key | `invalid_payload`, 저장 없음 | PASS |
| T-CHAT-DIRECT-07 | join 뒤 conversation 삭제·counterpart dormant | 매 send 재조회로 `not_found`/`unavailable` | PASS |
| T-CHAT-DIRECT-08 | direct DB commit 오류 | rollback, 두 participant 모두 미수신 | PASS |
| T-CHAT-ERROR-01 | handler 강제 exception | client generic `server_error`, event name-only log, body/token/traceback 없음 | PASS |
| T-CHAT-STALE-01 | HTTP logout 뒤 기존 socket | 즉시 disconnect, 이후 broadcast 미수신 | PASS |
| T-CHAT-STALE-02 | password 변경 | old socket 즉시 disconnect, 새 HTTP session socket connect | PASS |
| T-CHAT-STALE-03 | DB auth_version 증가 후 old send | event 전 disconnect, 저장 없음 | PASS |
| T-CHAT-STALE-04 | dormant 뒤 다른 user broadcast | broadcast 전 disconnect·미수신 | PASS |
| T-CHAT-STALE-05 | dormant→active 복구 | 과거 socket 미부활 | PASS |
| T-CHAT-STALE-06 | injected clock max age event/broadcast | stale sender/receiver 사전 disconnect | PASS |

## 최종 자동화 결과

2026-07-23 최종 검증 기준:

| 명령/범위 | 결과 |
|---|---|
| `.venv/bin/python -m pytest` | PASS, 408 tests |
| `.venv/bin/python -m pytest --cov=app --cov-report=term-missing` | PASS, app 96% |
| Ruff lint/format | PASS |
| Bandit app/scripts/run.py | PASS, finding 없음 |
| runtime/dev pip-audit | PASS, 알려진 취약점 없음 |
| pip check, compileall, diff check | PASS |
| Alembic 전체 이력·drift·route 확인 | PASS |

이 수치는 현재 Phase 04 `app` 코드 coverage이며 아직 미구현된 전체 과제 기능의 coverage가
아니다. 중간 실패는 수정 뒤 동일 범위를 재실행했으며 최종 결과와 별도로 최종 작업 보고에
원문과 해결 내용을 기록한다.

## 후속 테스트

| Phase | 범위 | 상태 |
|---|---|---|
| Phase 03 | 상품 CRUD·소유권, 이미지 위장/손상/path/pixel, 상품 검색 필터·정렬·pagination | 회귀 유지 |
| Phase 04 | Socket 인증, 전체/1대1 저장, sender 위조, 참여자 IDOR, stale lifecycle, event rate limit | 구현·검증 |
| Phase 05 | 신고 대상·중복/race·3명 제재, 관리자 role·복구·감사 | 예정 |
| Phase 06 | 송금 양수·자기·초과·rollback·동시성·멱등·원장 불변성과 최종 통합 | 예정 |
