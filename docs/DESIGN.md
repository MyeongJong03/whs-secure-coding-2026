# Design

## 구현 범위

Phase 01은 Flask application factory, 공통 보안 설정, foundation 모델, 최초 migration,
`/`, `/health`, 오류 처리와 회귀 테스트만 구현한다. 이 문서의 사용자·상품·검색·채팅·신고·
송금·관리자 경로는 공식 과제 요구사항을 빠짐없이 추적하기 위한 후속 설계이며 현재 동작하는
라우트나 UI가 아니다.

## 아키텍처

Flask application factory가 설정을 선택하고 확장을 초기화한 뒤 Blueprint를 등록한다. Jinja2
서버 렌더링과 SQLAlchemy ORM을 사용한다. HTTP/Socket.IO 경계는 요청 형식과 인증을,
향후 service 계층은 객체 권한·업무 규칙·트랜잭션을, model 계층은 SQLite 무결성을 담당한다.

```text
Browser/Socket client
        |
        v
Flask route or Socket event
  -> CSRF (HTTP state change) / authentication / input validation
  -> service authorization and transaction
  -> SQLAlchemy models -> SQLite
  -> escaped response or authorized event
                         +-> append-only Transfer / AuditLog semantics
```

## 디렉터리 구조

| 경로 | 책임 |
|---|---|
| `app/__init__.py` | factory, 확장 결합, user loader, 보안 헤더, 오류 처리 |
| `app/config.py` | Development/Testing/Production 설정과 Secret Key 검증 |
| `app/extensions.py` | 비결합 확장 객체와 SQLite PRAGMA |
| `app/models/` | foundation 데이터 모델과 DB 제약 |
| `app/main/` | 현재 공개 index와 health Blueprint |
| `app/templates/`, `app/static/` | 현재 foundation 화면과 로컬 정적 자산 |
| `migrations/` | 검토 가능한 최초 Alembic 스키마 이력 |
| `tests/` | factory, 인증 로더, 응답 보안, DB 제약 회귀 테스트 |
| `docs/` | 요구사항, 설계, 위협, Finding과 추적 자료 |

## 역할·권한표

`user`는 status가 `active`인 인증 사용자만 뜻한다. `dormant` 사용자는 공개 자원만 anonymous로
조회할 수 있고 로그인 및 기존 세션 인증은 거부한다. admin도 일반 기능을 사용할 때는 동일한
소유권·참여자 정책을 적용한다.

| 작업 | 비회원/dormant | active user | admin |
|---|---:|---:|---:|
| index, health | 허용 | 허용 | 허용 |
| 공개 사용자 조회·프로필 | 허용 | 허용 | 허용 |
| 공개 상품 목록·상세·검색 | 허용 | 허용 | 허용 |
| 회원가입·로그인 | 허용 | 현재 세션 정책에 따라 제한 | 별도 관리자 생성 정책 |
| POST 로그아웃·마이페이지·소개글·비밀번호 변경 | 거부 | 본인만 | 본인만 |
| 상품 등록·본인 상품 목록 | 거부 | 허용 | 일반 상품 흐름에서는 허용 |
| 상품 수정·삭제·판매 상태 변경 | 거부 | 본인 상품만 | 일반 상품 흐름에서는 본인 상품만 |
| 전체 실시간 채팅 | 거부 | 허용 | 허용 |
| 1대1 대화 조회·전송 | 거부 | 대화 참여자만 | 참여자인 경우만 |
| 사용자·상품 신고 | 거부 | 자기 자신·자기 상품 제외 | 일반 신고 정책 적용 |
| 사용자 간 가상 포인트 송금 | 거부 | 자기 송금·잔액 초과 제외 | 일반 송금 정책 적용 |
| 사용자·상품 관리 | 거부 | 거부 | 허용 및 감사 필수 |
| 채팅 메시지·신고 검토 | 거부 | 거부 | 허용 및 감사 필수 |
| 송금 내역 관리자 조회 | 거부 | 거부 | 읽기 전용 허용 및 감사 필수 |
| 관리자 URL 전체 | 거부 | 서버측 role 검사로 거부 | 허용된 작업만 허용 |

클라이언트가 보낸 role, user ID, seller ID, sender ID와 객체 UUID는 권한 근거로 사용하지
않는다. 서버가 로그인 세션의 user ID로 DB role, status, 소유권과 대화 참여 관계를 매 요청과
이벤트마다 다시 확인한다. 일반 회원가입은 입력에서 role을 받지 않고 `user`로 고정한다.

## 데이터 모델과 DB 불변식

모든 식별자는 UUID 문자열이다. 모든 핵심 모델은 생성 시각을 가지며 변경 가능한 User,
Wallet, Product는 갱신 시각도 가진다.

| 모델 | 핵심 관계와 제약 |
|---|---|
| User | username UNIQUE/NOT NULL, role/status CHECK, `password_hash`만 저장, active status만 `is_active=True` |
| Wallet | `user_id`가 PK/FK인 User 1:1, 기본 100000, balance >= 0 |
| Product | seller FK, title/description 길이, price > 0, status CHECK |
| Report | reporter FK, target type/reason CHECK, reporter/type/target 복합 UNIQUE |
| DirectConversation | 두 User FK, `user1_id < user2_id` canonical CHECK, canonical pair UNIQUE |
| ChatMessage | sender FK, nullable conversation FK, body 길이 CHECK |
| Transfer | sender/recipient FK, amount > 0, 서로 다른 사용자 CHECK, idempotency key UNIQUE |
| AuditLog | nullable actor FK, action/target와 민감정보를 제외한 JSON details |

DirectConversation의 canonical CHECK 하나가 동일 사용자 조합과 역순 저장을 모두 DB에서
거부한다. service는 두 UUID를 `sorted()`한 뒤 `user1_id`, `user2_id`로 저장하고, UNIQUE가
동일 canonical pair의 재삽입과 동시 생성을 막는다. 이 불변식은 ORM 모델과 최초 migration에
동일하게 정의한다.

Report의 다형 `target_id`는 DB FK로 두 대상 테이블을 동시에 참조할 수 없으므로 service가
target type에 맞는 실제 대상, 자기 신고 여부와 소유권을 한 트랜잭션에서 검사한다.
ChatMessage의 `conversation_id`가 null이면 전체 채팅이고, 값이 있으면 해당 대화 참여자만
접근 가능한 1대1 채팅이다. 완료된 Transfer는 service에서 update/delete를 제공하지 않는
append-only 의미의 원장으로 취급한다. AuditLog details에는 비밀번호, Secret Key, 세션·쿠키·
토큰을 넣지 않는다.

## 상태 전이

| 대상 | 허용 전이 | 주체/조건 |
|---|---|---|
| User | active -> dormant | 서로 다른 유효 신고자 3명 또는 관리자 |
| User | dormant -> active | 관리자 검토 및 감사 |
| Product | active -> hidden | 서로 다른 유효 신고자 3명 또는 관리자 |
| Product | active/hidden -> sold | 소유자의 판매 상태 관리 흐름 |
| Product | active/hidden/sold -> deleted | 소유자 또는 허용된 관리자 정책 |
| Product | hidden -> active | 관리자 검토 및 감사 |
| Report | pending -> confirmed/rejected | 관리자 검토 및 감사 |

dormant 전환이 commit되면 Flask-Login user loader가 해당 User를 반환하지 않으므로 기존 세션도
다음 요청부터 anonymous가 된다. 비밀번호 변경 뒤 다른 세션을 무효화하는 `auth_version`은
Phase 02에서 User 컬럼, 로그인 시 세션 버전 저장, 매 요청 버전 비교와 테스트를 함께 추가한다.

## 현재 및 예정 라우트

### 현재 Phase 01 라우트

| Method | 경로 | 요구사항 | 상태 |
|---|---|---|---|
| GET | `/` | FR-001 | 구현 |
| GET | `/health` | FR-002 | 구현 |
| any | 오류 handler 400/403/404/429/500 | FR-003 | 구현 |

### Phase 02+ 예정 라우트

경로는 설계 예시이며 후속 구현 시 요구사항 ID와 함께 확정한다. 모든 상태 변경 HTTP 요청은
POST/PATCH/DELETE와 CSRF를 사용하고 GET으로 상태를 바꾸지 않는다.

| 영역 | Method/예정 경로 예 | 대응 요구사항 | 필수 보호 |
|---|---|---|---|
| auth | GET/POST `/auth/register`, GET/POST `/auth/login`, POST `/auth/logout` | FR-101~103, FR-109, FR-111~112 | 입력 검증, rate limit, CSRF, role 고정, dormant 차단 |
| users | GET `/users`, GET `/users/<uuid>`, GET `/me` | FR-104~106, FR-110 | 공개 필드 allowlist, 본인 정보 분리 |
| profile | POST `/me/bio`, POST `/me/password` | FR-107~108 | 인증, CSRF, 본인, 현재 비밀번호 재확인, 세션 무효화 |
| products | GET/POST `/products`, GET `/products/<uuid>` | FR-201~204, FR-211~212 | 공개 상태 필터, 등록 시 인증·CSRF·검증 |
| own products | GET `/me/products`, POST `/products/<uuid>/edit`, `/delete`, `/status` | FR-205~210 | 인증, CSRF, seller 객체 권한 |
| search | GET `/products?q=&status=&min_price=&max_price=&sort=&page=` | FR-301~305 | 정렬/status allowlist, 정수 범위, 페이지·자원 상한, hidden/deleted 제외 |
| global chat | GET `/chat`, Socket.IO global events | FR-401, FR-403 | 연결·이벤트 인증, 길이/rate limit, sender session 고정 |
| direct chat | GET/POST `/conversations`, GET `/conversations/<uuid>` 및 Socket.IO room | FR-402~404 | canonical pair, 두 참여자만 조회·전송·room join |
| reports | POST `/reports/users/<uuid>`, POST `/reports/products/<uuid>` | FR-501~507 | 인증, CSRF, 대상·소유권·사유·중복 검사 |
| transfers | GET/POST `/transfers` | FR-601~609 | 인증, CSRF, 양수·잔액·자기 송금 검사, 원자성·멱등성 |
| admin users | GET/POST `/admin/users...` | FR-701, FR-707 | 모든 handler의 admin role, CSRF, 감사 |
| admin products | GET/POST `/admin/products...` | FR-702, FR-707 | 모든 handler의 admin role, CSRF, 감사 |
| admin chat | GET/POST `/admin/messages...` | FR-703, FR-707 | admin role, 최소 공개, 상태 변경 감사 |
| admin reports | GET/POST `/admin/reports...` | FR-508, FR-704, FR-707 | admin role, CSRF, 복구와 감사의 원자성 |
| admin transfers | GET `/admin/transfers` | FR-705, FR-707 | admin role, 읽기 전용, 민감정보 최소화 |
| admin audit | GET `/admin/audit-logs` | FR-706~707 | admin role, 페이지네이션, 로그 민감정보 금지 |

## 데이터 흐름

### 사용자·인증

회원가입은 사용자명 중복을 확인하고 password를 scrypt hash로 변환하며 role=`user`,
status=`active`, Wallet balance=100000을 한 트랜잭션으로 생성한다. 로그인은 hash와 active
status를 확인한 뒤 기존 세션을 회전한다. POST 로그아웃은 CSRF 검증 후 세션을 제거한다.
공개 프로필과 사용자 조회는 필드 allowlist를 사용하고, 마이페이지 변경은 현재 사용자 ID만
대상으로 한다. 비밀번호 변경은 현재 password 재확인과 `auth_version` 증가를 포함한다.

### 상품·검색·이미지

상품 등록과 변경은 서버 세션에서 seller를 결정하고 제목·설명·양수 정수를 검증한다. 수정·
삭제·판매 상태 변경은 조회와 함께 seller 소유권을 검사한다. 공개 목록·상세·검색은 hidden과
deleted를 제외한다. 검색은 상품명/설명 조건, 상태/가격 필터, 정렬 allowlist, 안정적인 보조
정렬과 제한된 page size를 사용한다. 이미지는 전체 요청 5 MiB 제한 뒤 JPEG/PNG/WebP를
Pillow로 decode/verify하고 pixel 상한을 확인해 안전한 형식으로 재생성하며 랜덤 파일명과 고정
저장 루트를 사용한다.

### 전체·1대1 채팅

Socket 연결과 각 이벤트에서 active 인증을 확인하고 sender는 세션에서 결정한다. 전체 메시지는
`conversation_id=null`, 1대1 메시지는 canonical conversation FK로 저장한다. 대화 생성 시 두
UUID를 정렬하며 room join, 이력 조회와 전송 모두 user1/user2 참여 관계를 검사한다. 메시지
길이와 사용자별 rate limit을 HTTP 조회와 이벤트에 각각 적용한다.

### 신고·차단·복구

신고 생성은 reporter 인증, target type, 대상 존재, 자기 자신/자기 상품 금지, 사유 길이와
중복을 검사한다. DB 복합 UNIQUE로 race를 최종 방어한다. pending/유효 신고의 서로 다른
reporter 수를 한 트랜잭션에서 집계해 3명이면 상품은 hidden, 사용자는 dormant로 전환한다.
관리자 검토·복구는 Report와 대상 상태를 함께 변경하고 같은 트랜잭션에 AuditLog를 추가한다.

### 가상 포인트 송금

service는 sender/recipient를 잠금 또는 조건부 UPDATE가 가능한 방식으로 조회하고 양수 정수,
서로 다른 사용자, 잔액을 검사한다. idempotency key의 기존 Transfer를 먼저 조회한 뒤 sender
차감, recipient 증가와 새 원장을 단일 트랜잭션으로 commit하고 오류 시 전부 rollback한다.
SQLite 동시성 한계를 고려해 짧은 쓰기 트랜잭션과 경쟁 조건 테스트를 사용한다. UI에는 실제
금융 자산이 아닌 과제용 가상 포인트임을 표시한다.

### 관리자

`/admin` 아래 모든 handler는 공통 server-side admin role 검사를 통과해야 하며 일반 user는
URL을 직접 호출해도 403을 받는다. 사용자·상품·메시지·신고 변경은 actor, action, target,
시각과 민감정보를 제외한 세부 내용을 AuditLog에 남긴다. 송금 원장은 조회만 허용하고 관리자
수정·삭제 기능을 제공하지 않는다.

## 개발/테스트/운영 차이

| 설정 | Development | Testing | Production |
|---|---|---|---|
| SECRET_KEY | 환경의 무작위 키 필수 | 테스트 프로세스용 런타임 임의 키 | 환경의 무작위 키 필수 |
| Secret 검증 | trim 후 32자 이상, 알려진 placeholder 거부 | 런타임 생성값 허용 | trim 후 32자 이상, 알려진 placeholder 거부 |
| DB | 기본 `instance/market.db` | 독립 in-memory 또는 임시 파일 | 명시 DB URL 권장 |
| debug | 환경값, 기본 false | false | false |
| cookie Secure | false (로컬 HTTP) | false | true |
| transport | 로컬 HTTP/WS 가능 | 테스트 client | HTTPS/WSS 필수 |
| limiter 저장소 | `memory://` 허용 | `memory://` | 외부 공유 저장소 필수 |

SQLite instance 디렉터리와 DB 파일은 실행 계정에 필요한 최소 권한만 부여한다. memory
rate-limit 저장소는 단일 프로세스 과제 개발에만 적합하다. 운영에서는 HTTPS/WSS 종료,
외부 공유 rate-limit 저장소, secret rotation과 파일 권한을 배포 검증 항목으로 확인한다.

## 요구사항 추적 구조

```text
REQUIREMENTS ID
  -> 역할·권한표 / 예정 라우트 / 데이터 흐름
  -> model CHECK·UNIQUE·FK 또는 service 정책
  -> TEST_MATRIX 테스트 ID
  -> SECURITY_FINDINGS / THREAT_MODEL
  -> 실제 검증 명령과 최종 보고서 증거
```

| 요구사항 범위 | 주요 설계 절 | 테스트 단계 |
|---|---|---|
| FR-001~003 | 현재 Phase 01 라우트 | Phase 01 자동 테스트 |
| FR-101~112 | 사용자·인증 흐름, role/status | foundation 일부 검증, 업무 테스트 Phase 02 |
| FR-201~212, FR-301~305 | 상품·검색·이미지 흐름 | DB 일부 검증, 업무/권한/자원 테스트 Phase 02 |
| FR-401~404 | 전체·1대1 채팅 흐름 | canonical DB 검증, 이벤트/IDOR 테스트 Phase 03 |
| FR-501~508 | 신고·차단·복구 흐름 | 중복 DB 검증, service/관리자 테스트 후속 |
| FR-601~609 | 가상 포인트 송금 흐름 | DB 일부 검증, 원자성/동시성/멱등성 테스트 Phase 04 |
| FR-701~707 | 관리자 흐름과 역할·권한표 | 전체 관리자 URL role/감사 테스트 후속 |

Phase 01의 coverage 결과는 현재 `app` foundation 코드 범위만 측정하며, 아직 구현하지 않은
전체 과제 기능의 coverage를 나타내지 않는다.
