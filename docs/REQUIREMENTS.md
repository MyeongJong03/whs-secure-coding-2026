# Requirements

## 범위와 용어

Phase 01은 안전한 실행 기반을 확정했고 Phase 02는 인증·사용자 관리, Phase 03은
상품·이미지·검색, Phase 04는 안전한 전체·1대1 실시간 채팅, Phase 05는 신고·자동
제재·관리자 운영과 감사를 구현했다. Phase 06은 과제용 가상 포인트 송금과 최종 통합을
구현한다.
아래 업무 기능 요구사항은 공식 과제의 최소 범위를 유지한 채 실제 구현 단계와 상태를
추적한다. 모델이 존재한다는 사실만으로 후속 서비스나 UI가 구현된 것은 아니다. "가상
포인트"는 실제 금융 자산이나 결제 수단이 아닌 과제용 정수 값이다.

## Phase 01 기반 요구사항

| ID | 요구사항 | 상태 |
|---|---|---|
| FR-001 | 비회원도 공개 index를 조회할 수 있다. | Phase 01 구현 |
| FR-002 | `/health`는 서비스 상태를 JSON으로 반환한다. | Phase 01 구현 |
| FR-003 | 400, 403, 404, 405, 409, 413, 429, 500 오류를 안전한 공통 화면으로 반환한다. | Phase 01 기반 + Phase 03 확장 |

## 사용자 요구사항

| ID | 독립 요구사항 | 구현 단계 |
|---|---|---|
| FR-101 | 사용자는 사용자명과 비밀번호로 회원가입할 수 있다. | Phase 02 구현 |
| FR-102 | 사용자는 등록된 자격 증명으로 로그인할 수 있다. | Phase 02 구현 |
| FR-103 | 로그아웃은 CSRF 보호를 받는 POST 요청으로만 수행한다. | Phase 02 구현 |
| FR-104 | 허용된 검색 조건으로 사용자를 조회할 수 있다. | Phase 02 구현 |
| FR-105 | 비밀정보를 제외한 공개 사용자 프로필을 조회할 수 있다. | Phase 02 구현 |
| FR-106 | 인증 사용자는 마이페이지에서 자신의 정보를 조회할 수 있다. | Phase 02 구현 |
| FR-107 | 인증 사용자는 자신의 소개글을 변경할 수 있다. | Phase 02 구현 |
| FR-108 | 비밀번호 변경 전에 현재 비밀번호를 다시 확인한다. | Phase 02 구현 |
| FR-109 | 사용자명은 DB와 서비스 계층에서 중복을 방지한다. | Phase 01 DB + Phase 02 service 구현 |
| FR-110 | 사용자 정보는 DB에서 생성·조회·변경 상태를 관리한다. | Phase 01 DB + Phase 02 service 구현 |
| FR-111 | 휴면 사용자의 신규 로그인과 기존 로그인 세션 사용을 모두 차단한다. | Phase 02 구현 |
| FR-112 | 일반 회원가입 요청으로 admin 권한을 획득할 수 없다. | Phase 02 구현 |

비밀번호 변경 뒤 다른 세션까지 무효화하기 위한 `auth_version`은 Phase 02 모델·두 번째
migration·세션 저장·검증·회귀 테스트로 구현했다.

## 상품 요구사항

| ID | 독립 요구사항 | 구현 단계 |
|---|---|---|
| FR-201 | 인증 사용자는 상품을 등록할 수 있다. | Phase 03 구현 |
| FR-202 | 상품은 상품명, 설명, 가격, 이미지와 판매자 정보를 제공한다. | Phase 03 구현 |
| FR-203 | 비로그인 사용자도 공개 상품 목록을 조회할 수 있다. | Phase 03 구현 |
| FR-204 | 비로그인 사용자도 공개 상품 상세를 조회할 수 있다. | Phase 03 구현 |
| FR-205 | 인증 사용자는 본인이 등록한 상품 목록을 조회할 수 있다. | Phase 03 구현 |
| FR-206 | 상품 소유자는 본인 상품을 수정할 수 있다. | Phase 03 구현 |
| FR-207 | 상품 소유자는 본인 상품을 삭제 상태로 변경할 수 있다. | Phase 03 구현 |
| FR-208 | 상품 소유자는 본인 상품의 판매 상태를 관리할 수 있다. | Phase 03 구현 |
| FR-209 | 다른 사용자의 상품 수정 요청을 거부한다. | Phase 03 구현 |
| FR-210 | 다른 사용자의 상품 삭제 요청을 거부한다. | Phase 03 구현 |
| FR-211 | 상품 정보와 상태는 DB에서 관리한다. | Phase 01 DB + Phase 03 service/migration 구현 |
| FR-212 | 상품 이미지는 JPEG, PNG, WebP만 안전하게 처리한다. | Phase 03 구현 |

## 검색 요구사항

| ID | 독립 요구사항 | 구현 단계 |
|---|---|---|
| FR-301 | 상품명과 상품 설명을 대상으로 검색한다. | Phase 03 구현 |
| FR-302 | 허용된 상품 상태로 검색 결과를 필터링한다. | Phase 03 구현 |
| FR-303 | 최소·최대 가격 범위로 검색 결과를 필터링한다. | Phase 03 구현 |
| FR-304 | 서버 allowlist에 포함된 정렬 기준과 방향만 허용한다. | Phase 03 구현 |
| FR-305 | 검색 결과를 페이지네이션하고 hidden·deleted 상품은 제외한다. | Phase 03 구현 |

## 소통 요구사항

| ID | 독립 요구사항 | 구현 단계 |
|---|---|---|
| FR-401 | active 인증 사용자만 전체 실시간 채팅에 연결·참여할 수 있다. | Phase 04 구현 |
| FR-402 | 인증 사용자는 다른 active 사용자와 canonical 1대1 대화를 생성·재사용할 수 있고 자기 대화는 금지한다. | Phase 04 구현 |
| FR-403 | 전체 및 1대1 채팅 이력을 DB에 저장하고 권한 범위에서 최근·이전 page를 조회한다. | Phase 04 구현 |
| FR-404 | 1대1 대화의 두 참여자만 대화 목록·페이지·room·메시지에 접근할 수 있다. | Phase 04 구현 |

## 신고 및 차단 요구사항

| ID | 독립 요구사항 | 구현 단계 |
|---|---|---|
| FR-501 | 인증 사용자는 다른 사용자를 신고할 수 있다. | Phase 05 구현 |
| FR-502 | 인증 사용자는 다른 사용자의 상품을 신고할 수 있다. | Phase 05 구현 |
| FR-503 | 사용자·상품 신고에는 정책에 맞는 신고 사유가 필요하다. | Phase 05 구현 |
| FR-504 | 자기 자신과 자신이 소유한 상품은 신고할 수 없다. | Phase 05 구현 |
| FR-505 | 동일 신고자가 동일 대상을 중복 신고할 수 없다. | Phase 05 구현 |
| FR-506 | 서로 다른 신고자 3명이 같은 상품을 유효하게 신고하면 상품을 hidden 처리한다. | Phase 05 구현 |
| FR-507 | 서로 다른 신고자 3명이 같은 일반 사용자를 유효하게 신고하면 사용자를 dormant 처리한다. | Phase 05 구현; admin 자동 제재 제외 |
| FR-508 | 관리자는 신고를 검토하고 대상 상태를 복구할 수 있다. | Phase 05 구현 |

## 송금 요구사항

| ID | 독립 요구사항 | 구현 단계 |
|---|---|---|
| FR-601 | 회원가입과 CLI admin 생성 시 Wallet에 가상 포인트 100000을 지급한다. | Phase 02/05 구현, Phase 06 회귀 검증 완료 |
| FR-602 | 포인트가 실제 금융 자산이 아닌 과제용 가상 포인트임을 모든 Wallet UI와 문서에 명시한다. | Phase 06 구현·자동 검증 완료 |
| FR-603 | active 일반 사용자와 active admin은 다른 active 일반 사용자 또는 admin에게 가상 포인트를 송금할 수 있다. | Phase 06 구현·자동 검증 완료 |
| FR-604 | 자기 자신에게 송금할 수 없다. | Phase 01 DB + Phase 06 service 구현·자동 검증 완료 |
| FR-605 | 송금액은 1~1,000,000,000의 정수만 허용한다. | Phase 06 form/service/DB 구현·자동 검증 완료 |
| FR-606 | 현재 잔액을 초과하는 송금을 거부한다. | Phase 06 조건부 debit 구현·자동 검증 완료 |
| FR-607 | 원장 예약, 송신자 차감, 수신자 증가와 감사 로그를 단일 DB transaction으로 수행한다. | Phase 06 구현·자동 검증 완료 |
| FR-608 | 서버 생성 고엔트로 token과 sender-bound derived key를 사용하고 동일 요청 재전송은 기존 결과, 다른 payload 재사용은 conflict로 처리한다. | Phase 06 구현·자동 검증 완료 |
| FR-609 | 완료된 송금은 사용자·관리자 HTTP UI에서 수정·삭제하지 않는 원장 레코드로 보존한다. | Phase 06 구현·자동 검증 완료 |

## 관리자 요구사항

| ID | 독립 요구사항 | 구현 단계 |
|---|---|---|
| FR-701 | 관리자는 사용자 상태와 허용된 사용자 관리 작업을 수행할 수 있다. | Phase 05 구현 |
| FR-702 | 관리자는 상품 상태와 허용된 상품 관리 작업을 수행할 수 있다. | Phase 05 구현 |
| FR-703 | 관리자는 채팅 메시지를 검토·숨김·복구할 수 있다. | Phase 05 구현 |
| FR-704 | 관리자는 신고를 검토하고 처리할 수 있다. | Phase 05 구현 |
| FR-705 | 관리자는 송금 내역을 읽기 전용으로 조회할 수 있다. | Phase 05 구현 |
| FR-706 | 모든 성공한 관리자 상태 조치를 감사 로그에 기록한다. | Phase 05 구현 |
| FR-707 | 일반 사용자의 모든 관리자 URL 접근을 서버에서 거부한다. | Phase 05 구현 |

## 입력 정책

| 입력 | 정책 |
|---|---|
| 사용자명 | ASCII 영문 대·소문자, 숫자, 밑줄만 허용하며 4~32자 |
| 비밀번호 | 12~128자 |
| 소개글 | 최대 500자 |
| 상품명 | 1~100자 |
| 상품 설명 | 1~2000자 |
| 상품 가격 | 정수 1~1,000,000,000 |
| 송금 수신자 | 기존 username 정책을 적용하며 strip 뒤 서버에서 active 사용자와 Wallet을 조회 |
| 송금액 | bool·소수 제외 정수 1~1,000,000,000 |
| 송금 현재 비밀번호 | strip하지 않고 최대 128자이며 성공 여부만 검증하고 저장·반사하지 않음 |
| 송금 idempotency token | 서버 생성 43자 URL-safe 문자열만 허용하고 raw token은 DB·audit·로그·응답 표시에서 제외 |
| 이미지 | 실제 JPEG, PNG, WebP만 허용하고 SVG/GIF/BMP/TIFF/ICO/animation/손상 파일 거부 |
| 이미지 요청 | 전체 요청 5 MiB, 입력·재인코딩 결과 4 MiB, 각 변 4096px, 총 16,000,000 pixel |
| 채팅 메시지 | CRLF/CR→LF, NFC, strip 후 1~500 Unicode code point·UTF-8 1~2000 bytes; tab/newline 외 C0·NUL·DEL 거부 |
| 신고 사유 | CRLF/CR→LF, NFC, strip 후 10~500 code point·UTF-8 최대 2000 bytes; tab/newline 외 C0·NUL·DEL 거부 |
| 검색 | 길이·페이지 크기 상한, 상태/정렬 allowlist, 정수 가격 범위 |

## 비기능 요구사항

| ID | 요구사항 |
|---|---|
| NFR-001 | Python 3.12와 고정된 의존성으로 재현 가능해야 한다. |
| NFR-002 | application factory와 개발·테스트·운영 설정을 분리한다. |
| NFR-003 | 빈 SQLite DB는 전체 Alembic migration history upgrade로 생성 가능해야 한다. |
| NFR-004 | 자동 테스트는 외부 네트워크 없이 실행되어야 한다. |
| NFR-005 | 운영 확장 시 Flask-Limiter의 memory 저장소를 공유 외부 저장소로 교체한다. |
| NFR-006 | 요구사항, 설계, 테스트와 보안 Finding을 ID로 추적할 수 있어야 한다. |
| NFR-007 | 각 Phase coverage 수치는 현재 app 코드 범위로 한정하며 전체 과제 coverage로 표현하지 않는다. |
| NFR-008 | GitHub Actions는 Python 3.12에서 테스트, app coverage 90%, 정적·의존성 검사와 빈 DB migration drift 검사를 실제 repository secret 없이 수행한다. |

## 보안 요구사항

| ID | 요구사항 |
|---|---|
| SR-001 | Development·Production의 SECRET_KEY는 환경에서 제공한 32자 이상 무작위 문자열이어야 하며 누락·공백·짧은 값·알려진 placeholder를 거부한다. |
| SR-002 | 비밀번호는 Werkzeug 안전한 기본 scrypt로 해시하며 원문을 저장하지 않는다. |
| SR-003 | 모든 상태 변경에 전역 CSRF 보호를 적용한다. |
| SR-004 | 인증, 객체 소유권·대화 참여 관계와 관리자 role을 서버에서 검사한다. |
| SR-005 | 모든 사용자 입력을 서버에서 형식·길이·범위 검증한다. |
| SR-006 | ORM/바인딩을 사용하고 동적 SQL 문자열 결합을 금지한다. |
| SR-007 | 세션 쿠키에 HttpOnly와 SameSite=Lax를 적용하고 운영에서는 Secure를 적용한다. |
| SR-008 | 중앙 보안 헤더와 제한적인 CSP를 모든 응답에 적용한다. |
| SR-009 | 오류 응답에 스택, 로컬 경로, 내부 예외를 노출하지 않는다. |
| SR-010 | DB의 CHECK, UNIQUE, NOT NULL, FOREIGN KEY로 핵심 무결성을 강제한다. |
| SR-011 | AuditLog에 비밀번호, Secret Key, 세션 값이나 인증 토큰을 기록하지 않는다. |
| SR-012 | 업로드는 확장자와 실제 이미지 형식을 검증하고 재생성·랜덤 저장명을 적용한다. |
| SR-013 | 송금 원장 예약, 조건부 debit, credit와 `transfer.created` AuditLog를 단일 DB transaction으로 처리하고 실패를 전체 rollback한다. |
| SR-014 | 모든 관리자 기능에서 서버측 role을 검사하고 관리자 상태 변경을 감사한다. |
| SR-015 | dormant 사용자는 Flask-Login user loader에서 거부하며 비밀번호 변경 세션 무효화는 `auth_version`으로 구현한다. |
| SR-016 | 검색 정렬은 allowlist로 제한하고 페이지 크기·검색 입력·쿼리 자원을 제한한다. |
| SR-017 | Socket connect는 same-origin과 Flask-WTF CSRF, active 인증, exact DB auth_version을 확인하고 event마다 다시 검증한다. |
| SR-018 | 채팅 sender와 room은 서버 인증 사용자·canonical conversation에서만 파생하고 client 식별자·room을 신뢰하지 않는다. |
| SR-019 | logout·password 변경은 해당 사용자의 Socket을 즉시 종료하고 event/broadcast 전 dormant·version·age stale connection을 제거한다. |
| SR-020 | 채팅 event는 strict payload, 사용자 합산 sliding-window limit, bounded packet과 commit 성공 후 room broadcast를 적용한다. |
| SR-021 | raw idempotency token은 저장·로그·표시하지 않고 sender-bound SHA-256 key와 DB UNIQUE로 동일 요청을 한 번만 반영하며 payload 불일치는 conflict로 거부한다. |
| SR-022 | 송금 sender는 current user, recipient는 username server lookup으로 결정하고 history/detail은 participant query와 최소 projection DTO만 사용한다. |

## Phase 01 수용 기준

| ID | 기준 |
|---|---|
| AC-001 | Testing 설정에서 factory, CSRF, 런타임 임의 Secret Key와 임시 DB가 동작한다. |
| AC-002 | Development·Production에서 SECRET_KEY 누락·짧은 값·예제 placeholder·legacy 고정값은 시작을 거부하고 32자 이상 임의 값은 허용한다. |
| AC-003 | index와 health가 200을 반환하고 지정 보안 헤더가 존재한다. |
| AC-004 | 404와 500 응답 본문에 내부 예외·스택·로컬 경로가 없다. |
| AC-005 | SQLite foreign_keys와 모델의 필수 UNIQUE/CHECK 제약 테스트가 통과한다. |
| AC-006 | DirectConversation은 `user1_id < user2_id`와 canonical pair UNIQUE를 DB에서 강제한다. |
| AC-007 | active 세션은 인증되고 dormant 전환 뒤 기존 세션의 다음 요청은 anonymous로 처리된다. |
| AC-008 | 최초 migration이 빈 SQLite DB에 upgrade되고 별도 두 번째 migration이 없다. |
| AC-009 | pytest, coverage, Ruff, Bandit, pip-audit, compileall, pip check와 diff check 결과를 사실대로 기록한다. |

`AC-008`은 `phase-01-foundation` 태그 시점의 수용 기준이다. Phase 02는 최초 migration을
변경하지 않고 별도의 두 번째 revision을 추가한다.

## Phase 02 수용 기준

| ID | 기준 |
|---|---|
| AC-101 | 가입은 정책 입력만 받고 User·Wallet 100000을 한 transaction으로 만들며 권한 필드를 무시한다. |
| AC-102 | 로그인은 active 사용자만 허용하고 일반 오류·dummy hash·IP rate limit을 적용하며 세션을 회전한다. |
| AC-103 | 로그아웃·소개글·비밀번호 변경은 POST, 인증, CSRF를 요구한다. |
| AC-104 | user loader는 active와 정확한 `auth_version`을 확인하고 거부 시 인증 키를 제거한다. |
| AC-105 | dormant 뒤 재활성화된 과거 세션과 비밀번호 변경 전 다른 client 세션은 인증되지 않는다. |
| AC-106 | 사용자 목록·프로필은 active의 `username`, `bio`만 DB SELECT projection에 포함하고, 전체 User ORM 객체가 아닌 이 두 필드 전용 공개 view DTO를 template에 전달하며 고정 20개 SQL 페이지네이션을 사용한다. |
| AC-107 | 마이페이지는 현재 사용자의 username·bio·balance만 보여 주며 가상 포인트 고지를 포함한다. |
| AC-108 | 소개글은 500자 경계를 검사하고 autoescape를 유지하며 다른 사용자 식별자를 무시한다. |
| AC-109 | 비밀번호 변경은 현재 비밀번호, 길이·확인·동일 여부를 검사하고 hash와 버전을 한 transaction으로 변경한다. |
| AC-110 | 두 번째 migration은 빈 DB upgrade, 첫 revision downgrade·re-upgrade와 drift check를 통과한다. |
| AC-111 | CSRF는 Testing에서도 활성이고 limiter 상태만 fixture에서 reset하며 rate-limit 시험은 활성 상태다. |
| AC-112 | 전체 자동·정적·의존성·migration 검증 결과와 app coverage를 실제 결과대로 기록한다. |

## 단계 구분과 제외 범위

- Phase 02: 인증 및 사용자 관리 — 보존·회귀 유지
- Phase 03: 상품, 안전한 이미지 업로드, 상품 검색 — 보존·회귀 유지
- Phase 04: 전체 및 1대1 채팅 — 보존·회귀 유지
- Phase 05: 신고, 자동 제재, 관리자 기능 — `phase-05-moderation-admin` 태그로 보존·회귀 유지
- Phase 06: 가상 포인트 송금, 최종 통합 및 보안 강화 — 구현·로컬 자동 검증 완료

가상 포인트는 과제용 정수 원장일 뿐 실제 은행·카드·결제·환전·충전·출금·환불 자산이
아니다. 영구 cloud 배포와 외부 결제 연동은 범위 밖이다.

## Phase 03 수용 기준

| ID | 기준 |
|---|---|
| AC-201 | 생성은 현재 로그인 User를 seller로 고정하고 title/description/price/필수 안전 이미지만 받아 active 상품과 파일을 일관되게 만든다. |
| AC-202 | 공개 목록·상세는 active/sold 및 active seller만 SQL projection DTO로 제공하고 private ORM 필드를 template에 전달하지 않는다. |
| AC-203 | 소유자 목록은 자기 상품의 모든 상태를 DTO로 제공하고 타인 상품은 포함하지 않는다. |
| AC-204 | 수정은 본인 active/sold의 허용 필드와 선택 이미지에 한하며 타인·없는·hidden/deleted 상품은 동일 404다. |
| AC-205 | 소유자 전이는 active↔sold만 허용하고 hidden/deleted 복구를 거부하며 delete는 row와 파일을 유지한 채 deleted로 바꾼다. |
| AC-206 | 이미지 입력은 byte/format/dimension/pixel/frame/extension을 검증하고 방향 정규화, metadata 제거, RGB/RGBA 변환, 재인코딩을 수행한다. |
| AC-207 | 파일은 web root 밖 random name으로 0700/0600 저장하고 안전한 pattern·regular file·size·format·symlink 검사를 통과한 경우만 제공한다. |
| AC-208 | 파일 저장과 DB commit 실패 cleanup, 이미지 교체의 이전 파일 보존/성공 후 제거 순서를 자동 검증한다. |
| AC-209 | 검색은 q 100자, 공개 상태, 가격 1~1,000,000,000, 정렬 allowlist, page 1~1000, fixed 20을 SQL에서 적용한다. |
| AC-210 | 모든 mutation은 인증·CSRF·사용자 rate limit, 공개 조회는 IP rate limit, 관리 응답은 no-store를 적용한다. |
| AC-211 | 세 번째 migration은 기존 두 migration을 변경하지 않고 head upgrade, Phase 02 downgrade, 재-upgrade와 drift check를 통과한다. |
| AC-212 | 상품·이미지·검색 자동 테스트와 Phase 04 시작 시점의 기존 307개 회귀를 유지하고 전체 품질·보안 검증 결과를 사실대로 기록한다. |

## Phase 04 수용 기준

| ID | 기준 |
|---|---|
| AC-401 | `/chat`·`/chat/direct`·`/chat/direct/<uuid>`는 active 로그인과 IP 60/minute, page 1~1000, `no-store, private`를 적용하고 고정 50/20 SQL page를 DTO로 제공한다. |
| AC-402 | direct start는 CSRF POST와 사용자 20/hour를 요구하고 username으로 active target을 조회하며 자기 대화를 거부하고 canonical pair UNIQUE race에서 기존 row를 재조회한다. |
| AC-403 | direct route/event는 매번 participant query를 사용하고 타인·없는 conversation을 같은 404 또는 generic `not_found`로 처리하며 server-only room만 join한다. |
| AC-404 | connect auth는 exact CSRF payload, Flask-WTF 검증, active 인증·DB version, same-origin, 사용자당 5개 cap을 만족해야 하고 Flask session을 변경하지 않는다. |
| AC-405 | 모든 inbound event 전에 registry, current authenticated user, DB status/version과 최대 1800초를 재검증하고 실패 socket을 generic 오류로 종료한다. |
| AC-406 | logout과 password 변경 commit 뒤 기존 `/chat` socket을 즉시 종료하며 dormant/version/age socket은 다음 event 또는 broadcast 전에 제거되고 재활성화해도 부활하지 않는다. |
| AC-407 | global/direct send는 client sender·room을 받지 않고 server user를 sender로 저장하며 DB commit 성공 뒤 해당 server room에만 allowlisted payload를 emit한다. |
| AC-408 | message는 exact schema, NFC·newline·strip, 1~500 code point, UTF-8 1~2000 bytes와 control 정책을 적용하고 malformed 시에도 사용자 message quota를 소비한다. |
| AC-409 | global/direct 합산 message 5/10초·120/hour와 join 30/60초 monotonic limiter를 app별로 격리하고 여러 socket 우회를 차단한다. |
| AC-410 | local Socket.IO 4.8.3 bundle은 공식 byte와 SHA-384가 일치하고 MIT notice·local SRI를 포함하며 runtime CDN과 inline script/style을 사용하지 않는다. |
| AC-411 | 네 번째 migration만 추가해 boolean CHECK와 named index 4개를 만들고 Phase 03 downgrade·head re-upgrade·두 drift check에서 기존 schema를 보존한다. |
| AC-412 | 기존 307개 테스트를 유지하고 HTTP·DB·Socket·room·static integrity·stale lifecycle을 추가 검증하며 app coverage 90% 이상과 품질 명령 결과를 사실대로 기록한다. |

## Phase 05 수용 기준

| ID | 기준 |
|---|---|
| AC-501 | 신고자, target type과 target은 current user와 URL로 서버에서 결정하고 active 사용자 또는 active/sold 상품만 허용하며 자기 사용자·상품을 거부한다. |
| AC-502 | reason은 공통 LF/NFC/strip, 10~500 code point, UTF-8 2000 bytes와 control 정책을 통과하며 출력은 autoescape하고 감사 details에 복제하지 않는다. |
| AC-503 | reporter-target UNIQUE의 사전 검사와 IntegrityError race를 처리하고 사용자·상품 POST가 사용자 기준 shared 10/hour를 사용한다. |
| AC-504 | `pending`/`confirmed`만 유효 count로 사용하고 서로 다른 3번째 신고에서 상품 이전 active/sold 상태를 저장해 hidden 처리하거나 일반 사용자를 dormant 처리한다. admin 신고는 저장하되 자동 dormant하지 않는다. |
| AC-505 | 신고·대상 상태·system audit는 한 transaction이며 user dormant commit 뒤 `auth_version` 증가 상태로 모든 Socket을 종료한다. |
| AC-506 | admin은 CLI hidden password prompt로만 만들고 기본 credential·web role 변경 없이 User+Wallet+AuditLog를 원자 생성한다. |
| AC-507 | 모든 `/admin` route는 active admin을 서버에서 검사하고 GET 120/minute, mutation shared user 60/hour, CSRF와 현재 password 재확인, route-derived target과 action allowlist를 적용한다. |
| AC-508 | 사용자 active↔dormant는 실제 전이마다 version을 증가시키고 commit 뒤 disconnect한다. 자기 dormant와 마지막 active admin 제거를 막으며 과거 cookie/Socket은 복구 뒤에도 무효다. |
| AC-509 | 상품 hide/restore/delete는 previous status 정책을 적용하고 row·image를 유지한다. 신고 decision과 message visibility도 audit와 한 transaction이다. |
| AC-510 | 관리자 Transfer는 고정 50개 SQL page의 읽기 전용 projection이며 idempotency key와 내부 user ID를 표시하지 않는다. |
| AC-511 | AuditLog details는 action별 scalar allowlist만 허용하고 password/hash/secret/CSRF/session/cookie/version/idempotency/sid/reason/token을 거부한다. UI는 projection·autoescape·읽기 전용이다. |
| AC-512 | 다섯 번째 migration만 추가하고 기존 네 파일을 보존하며 Phase 04 downgrade, re-upgrade, 두 drift check와 named CHECK/index introspection을 통과한다. |
| AC-513 | Phase 04의 기존 408개 테스트를 유지하고 DB·HTTP·Socket disconnect·audit·CLI·RBAC 회귀를 추가하며 app coverage 90% 이상을 실제 명령으로 검증한다. |

유효 신고 수는 동일 `target_type`·`target_id`에서 status가 `pending` 또는 `confirmed`인
row 수다. UNIQUE 때문에 서로 다른 신고자 수와 같다. `rejected`는 이후 count에서 제외한다.
admin 대상은 계정 가용성 DoS를 줄이기 위해 자동 dormant하지 않고 다른 active admin의
수동 검토·사용자 상태 route만 허용한다.

## Phase 06 수용 기준

| ID | 기준 |
|---|---|
| AC-601 | 회원가입과 CLI admin 생성의 Wallet 100000 회귀를 유지하고 모든 Wallet 화면에 과제용 가상 포인트 고지를 표시한다. |
| AC-602 | `/wallet`, `/wallet/transfer`, `/wallet/transfers/<uuid>`는 active 로그인과 `no-store, private`를 적용하고 GET은 IP 60/minute, POST는 사용자 3/minute·10/hour를 적용한다. |
| AC-603 | sender는 current user, recipient는 strip한 username의 active User와 Wallet server query로 결정한다. client sender/recipient ID, balance와 DB key는 받거나 신뢰하지 않는다. |
| AC-604 | 송금은 strip하지 않는 current password, amount 정수 1~1,000,000,000과 정확한 43자 URL-safe raw token을 form과 service에서 다시 검증한다. |
| AC-605 | raw token은 응답 표시·flash·로그·DB·audit에 남기지 않고 `sha256(sender_id + ":" + token)` 64자리 소문자 hex만 Transfer UNIQUE key로 저장한다. |
| AC-606 | 같은 derived key와 같은 recipient/amount는 기존 transfer를 반환하고 추가 차감·증가·원장·audit를 만들지 않으며 다른 payload는 409 conflict와 전체 불변 상태로 처리한다. |
| AC-607 | Transfer flush 예약 뒤 `balance >= amount` 조건부 debit과 정확한 rowcount를 사용하고 credit·`transfer.created` amount-only audit를 포함해 한 번만 commit한다. |
| AC-608 | 잔액 부족, sender/recipient Wallet 누락, credit rowcount, audit, commit과 기타 DB 실패는 sender·recipient balance, Transfer와 AuditLog를 모두 rollback한다. |
| AC-609 | file SQLite의 독립 session/thread에서 서로 다른 token 80+80/잔액 100과 같은 token 동시 요청을 검증해 음수 잔액·이중 차감·중복 원장을 막고 Wallet 총합을 보존한다. |
| AC-610 | history는 current user sender/recipient 조건, direction/sort/page allowlist, fixed 20 SQL LIMIT/OFFSET과 created_at/id 안정 정렬을 사용하며 필요한 column만 frozen slots DTO로 전달한다. |
| AC-611 | detail은 sender 또는 recipient participant query만 허용하고 제3자와 missing을 같은 404로 처리한다. 사용자·관리자 Transfer UI는 원장 수정·삭제 route를 제공하지 않는다. |
| AC-612 | 여섯 번째 migration 하나만 추가해 bounded amount와 key format named CHECK, sender/recipient history index를 만들고 기존 unique/FK/distinct-user 제약을 보존한다. 기존 다섯 파일은 byte 단위 불변이다. |
| AC-613 | GitHub Actions와 로컬 명령에서 기존 518개 테스트를 삭제·skip·약화하지 않고 Phase 06 DB·HTTP·rollback·idempotency·concurrency·audit 테스트를 추가하며 app coverage 90% 이상, 품질·보안·migration 검증 결과를 사실대로 기록한다. |

## 상품 상태 전이와 이미지 정책

| 현재 상태 | 공개 | 소유자 수정 | 소유자 상태 전이 | 소유자 delete |
|---|---:|---:|---|---:|
| active | active seller일 때 가능 | 가능 | sold 또는 같은 active | deleted |
| sold | active seller일 때 가능 | 가능 | active 또는 같은 sold | deleted |
| hidden | 불가 | 불가 | 불가 | deleted |
| deleted | 불가 | 불가 | 불가 | 재삭제·복구 불가 |

신규 상품은 이미지가 필수다. legacy migration row 때문에 DB column은 nullable을 유지한다.
원본 filename, seller/status/image filename/timestamp client 필드는 신뢰하지 않는다. 실제
JPEG/PNG/WebP만 정규화 확장자로 재인코딩하며 저장 결과도 4 MiB 이하여야 한다.

## 요구사항 추적 구조

| 요구사항 범위 | 설계 위치 | 현재 테스트 | 현재 구현 상태 |
|---|---|---|---|
| FR-001~003 | DESIGN의 현재 라우트·오류 흐름 | T-APP-05~09 | Phase 01 구현 |
| FR-101~112 | DESIGN의 인증·사용자 route/service/session 흐름 | T-AUTH-*, T-USER-*, T-MIG-02~05 | Phase 02 구현 |
| FR-201~212 | DESIGN의 상품 route/service·이미지 경계·transaction | T-PRODUCT-*, T-IMAGE-*, T-MIG-07~ | Phase 03 구현 |
| FR-301~305 | DESIGN의 검색 query와 allowlist | T-SEARCH-* | Phase 03 구현 |
| FR-401~404 | DESIGN의 chat HTTP/Socket/registry/room/transaction 흐름 | T-CHAT-HTTP-*, T-CHAT-CONNECT-*, T-CHAT-GLOBAL-*, T-CHAT-DIRECT-*, T-CHAT-STALE-* | Phase 04 구현 |
| FR-501~508 | DESIGN의 moderation transaction·threshold·복구 흐름 | T-P05-REPORT-*, T-P05-AUTO-* | Phase 05 구현 |
| FR-601~609 | DESIGN의 Wallet token·conditional debit·원자 transaction·history projection 흐름 | T-AUTH-REG-*, T-P05-CLI-*, T-P06-* | Phase 06 구현·자동 검증 완료 |
| FR-701~707 | DESIGN의 CLI/RBAC/admin service/DTO/audit 흐름 | T-P05-CLI-*, T-P05-ADMIN-*, T-P05-AUDIT-* | Phase 05 구현 |
| SR-001~022 | DESIGN·THREAT_MODEL·SECURITY_FINDINGS | TEST_MATRIX의 자동·도구 검증 | Phase 06 로컬 자동 검증 완료 |
| NFR-001~008 | DESIGN·README·GitHub Actions | T-MIG-*, T-CHAT-STATIC-*, T-P05-*, T-P06-*, T-TOOL-* | CI workflow·로컬 검증 완료, 실제 GitHub Actions 실행은 수동 확인 예정 |
