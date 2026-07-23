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

## 최종 자동화 결과

2026-07-23 최종 검증 기준:

| 명령/범위 | 결과 |
|---|---|
| `.venv/bin/python -m pytest` | PASS, 143 tests |
| `.venv/bin/python -m pytest --cov=app --cov-report=term-missing` | PASS, app 99% |
| Ruff lint/format | PASS |
| Bandit app/run.py | PASS, High/Medium 미해결 finding 없음 |
| runtime/dev pip-audit | PASS, 알려진 취약점 없음 |
| pip check, compileall, diff check | PASS |
| Alembic 전체 이력·drift·route 확인 | PASS |

이 수치는 현재 Phase 02 `app` 코드 coverage이며 아직 미구현된 전체 과제 기능의 coverage가
아니다. 중간 실패는 수정 뒤 동일 범위를 재실행했으며 최종 결과와 별도로 최종 작업 보고에
원문과 해결 내용을 기록한다.

## 후속 테스트

| Phase | 범위 | 상태 |
|---|---|---|
| Phase 03 | 상품 CRUD·소유권, 이미지 위장/손상/path/pixel, 상품 검색 필터·정렬·pagination | 예정 |
| Phase 04 | Socket 인증, 전체/1대1 저장, sender 위조, 참여자 IDOR, event rate limit | 예정 |
| Phase 05 | 신고 대상·중복/race·3명 제재, 관리자 role·복구·감사 | 예정 |
| Phase 06 | 송금 양수·자기·초과·rollback·동시성·멱등·원장 불변성과 최종 통합 | 예정 |
