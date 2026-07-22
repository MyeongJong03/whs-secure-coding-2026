# Test Matrix

## Phase 01 자동 테스트

| 요구사항 ID | 테스트 ID | 테스트 종류 | 정상/비정상 조건 | 예상 결과 | 자동화 | 현재 상태 |
|---|---|---|---|---|---|---|
| NFR-002, AC-001 | T-APP-01 | unit/config | Testing factory 정상 | 앱, in-memory DB, 런타임 임의 key 설정 | pytest | PASS (2026-07-22) |
| SR-001, AC-002 | T-APP-02 | negative/config | Development·Production key 누락 | RuntimeError로 시작 거부 | pytest | PASS (2026-07-22) |
| SR-001, AC-002 | T-APP-03 | negative/config | 비문자열·빈 값·공백·짧은 key | RuntimeError로 시작 거부 | pytest | PASS (2026-07-22) |
| SR-001, AC-002 | T-APP-04 | negative/config | `.env.example` placeholder | RuntimeError로 시작 거부 | pytest | PASS (2026-07-22) |
| SR-001, AC-002 | T-APP-05 | negative/config | legacy 고정값 | RuntimeError로 시작 거부 | pytest | PASS (2026-07-22) |
| SR-001, AC-002 | T-APP-06 | unit/config | trim 후 32자 이상 임의 key | Development·Production 생성 허용 및 trim 값 사용 | pytest | PASS (2026-07-22) |
| SR-003 | T-APP-07 | unit/config | Testing CSRF | extension 활성 | pytest | PASS (2026-07-22) |
| FR-002 | T-APP-08 | HTTP | GET `/health` | 200, `{"status":"ok"}` | pytest | PASS (2026-07-22) |
| FR-001 | T-APP-09 | HTTP | GET `/` | 200, foundation 화면 | pytest | PASS (2026-07-22) |
| SR-008 | T-APP-10 | HTTP/security | 정상 응답 | 필수 header 존재 | pytest | PASS (2026-07-22) |
| FR-003, SR-009 | T-APP-11 | negative/HTTP | 없는 경로 | 404, 내부 정보 없음 | pytest | PASS (2026-07-22) |
| FR-003, SR-009 | T-APP-12 | negative/HTTP | 내부 예외 | 500, 예외·경로 없음 | pytest | PASS (2026-07-22) |
| FR-111, SR-015, AC-007 | T-APP-13 | auth/session | active user ID를 가진 세션 요청 | user loader가 User를 반환해 authenticated | pytest, tests-only route | PASS (2026-07-22) |
| FR-111, SR-015, AC-007 | T-APP-14 | negative/auth/session | 인증 뒤 같은 User를 dormant로 변경 | 기존 세션의 다음 요청이 anonymous | pytest, tests-only route | PASS (2026-07-22) |
| SR-010 | T-DB-01 | integration/DB | SQLite 연결 | `foreign_keys=1` | pytest | PASS (2026-07-22) |
| FR-109, SR-010 | T-DB-02 | negative/DB | username 중복 | commit 거부 | pytest | PASS (2026-07-22) |
| FR-601, FR-606, SR-010 | T-DB-03 | DB | Wallet 기본값·음수 | 100000, 음수 commit 거부 | pytest | PASS (2026-07-22) |
| FR-202, SR-010 | T-DB-04 | negative/DB | product price <= 0 | commit 거부 | pytest | PASS (2026-07-22) |
| FR-505, SR-010 | T-DB-05 | negative/DB | 동일 reporter/type/target | commit 거부 | pytest | PASS (2026-07-22) |
| FR-605, SR-010 | T-DB-06 | negative/DB | transfer amount <= 0 | commit 거부 | pytest | PASS (2026-07-22) |
| FR-604, SR-010 | T-DB-07 | negative/DB | sender=recipient | commit 거부 | pytest | PASS (2026-07-22) |
| FR-404, SR-010, AC-006 | T-DB-08 | negative/DB | 같은 UUID를 user1/user2에 저장 | canonical CHECK로 commit 거부 | pytest | PASS (2026-07-22) |
| FR-404, SR-010, AC-006 | T-DB-09 | positive/DB | 실제 두 UUID를 `sorted()`한 조합 | `user1_id < user2_id` 저장 성공 | pytest | PASS (2026-07-22) |
| FR-404, SR-010, AC-006 | T-DB-10 | negative/DB | 같은 canonical pair 재삽입 | UNIQUE로 commit 거부 | pytest | PASS (2026-07-22) |
| FR-404, SR-010, AC-006 | T-DB-11 | negative/DB | 실제 UUID의 역순 조합 직접 삽입 | DB canonical CHECK로 commit 거부 | pytest | PASS (2026-07-22) |
| FR-111, SR-015 | T-DB-12 | unit/model | User status=active | `is_active is True` | pytest | PASS (2026-07-22) |
| FR-111, SR-015 | T-DB-13 | unit/model | User status=dormant | `is_active is False` | pytest | PASS (2026-07-22) |
| SEC-01 | T-SRC-01 | static regression | legacy 고정 secret 원문 | app source에 없음 | pytest | PASS (2026-07-22) |
| SR-002 | T-SRC-02 | model inspection | 원문 password 컬럼 | 존재하지 않음 | pytest | PASS (2026-07-22) |
| SR-002 | T-SRC-03 | unit/security | password 설정 | scrypt hash/검증 성공 | pytest | PASS (2026-07-22) |

인증 상태 관찰용 `/_test/auth-state` route는 테스트가 fixture application에만 등록하며 운영
application source에는 존재하지 않는다. dormant 기존 세션 검증은 첫 authenticated 응답 뒤 DB
상태를 변경하고 동일 client의 다음 요청을 검사한다.

## migration·도구 검증

| 요구사항 ID | 테스트 ID | 검증 | 성공 기준 | 현재 상태 |
|---|---|---|---|---|
| NFR-003, AC-006, AC-008 | T-MIG-01 | 임시 빈 SQLite에 최초 migration upgrade와 `flask db check` | upgrade/check 성공, canonical CHECK와 UNIQUE 존재, 임시 DB 삭제 | PASS (2026-07-22) |
| NFR-001, AC-009 | T-TOOL-01 | pytest와 `--cov=app` | 전체 테스트 통과, foundation 범위 coverage 기록 | PASS: 48 tests, foundation 99% (2026-07-22) |
| NFR-001, AC-009 | T-TOOL-02 | Ruff lint/format | 위반 없음 | PASS (2026-07-22) |
| SR-006, AC-009 | T-TOOL-03 | Bandit `app run.py` | 미해결 보안 경고 없음 | PASS (2026-07-22) |
| NFR-001, AC-009 | T-TOOL-04 | runtime/dev pip-audit | 알려진 취약점 없음 | PASS (2026-07-22) |
| NFR-001, AC-009 | T-TOOL-05 | compileall, pip check, diff check | 오류·불일치 없음 | PASS (2026-07-22) |

Phase 01에서 보고하는 coverage는 현재 `app` foundation 코드 범위만 측정한다. 회원가입,
로그인 UI, 상품 CRUD·검색, 채팅, 신고 서비스, 송금과 관리자 기능이 아직 구현되지 않았으므로
해당 수치를 전체 과제의 coverage로 해석하거나 표현하지 않는다.

## 후속 업무 테스트

| 요구사항 범위 | 테스트 ID | 필수 테스트 범위 | 현재 상태 |
|---|---|---|---|
| FR-101~112 | T-FUTURE-USER-* | 가입·로그인·POST 로그아웃·조회·프로필·재인증·중복·dormant·admin 상승 거부 | Phase 02 예정 |
| FR-201~212 | T-FUTURE-PRODUCT-* | 공개 조회, 소유권 CRUD/status, 타인 거부, DB, JPEG/PNG/WebP 및 위장 파일 | Phase 02 예정 |
| FR-301~305 | T-FUTURE-SEARCH-* | title/description, 상태/가격, sort allowlist, page limit, hidden/deleted 제외 | Phase 02 예정 |
| FR-401~404 | T-FUTURE-CHAT-* | 인증 전체/1대1, 저장·조회, sender 위조, 비참여자 IDOR, rate limit | Phase 03 예정 |
| FR-501~508 | T-FUTURE-REPORT-* | user/product, 사유, 자기 대상, 중복/race, 2명/3명, 관리자 복구 | Phase 02/관리자 단계 예정 |
| FR-601~609 | T-FUTURE-TRANSFER-* | 초기 포인트, 가상 포인트 표시, 양수/자기/초과, rollback, 동시성, 멱등, 원장 불변성 | Phase 04 예정 |
| FR-701~707 | T-FUTURE-ADMIN-* | 모든 관리자 URL role 거부, 관리 기능, 메시지/신고, 송금 조회, 감사 로그 | 관리자 단계 예정 |

실패한 테스트를 삭제하거나 skip으로 숨기지 않으며, 최종 상태는 실제 명령 결과와 일치시킨다.
