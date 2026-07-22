# Threat Model

## 범위와 자산

범위는 브라우저, Flask/Jinja2 애플리케이션, Socket.IO 경계, SQLite와 업로드 저장소다.

- 계정 식별자, 비밀번호 해시, 세션과 role
- 프로필·상품·이미지·전체/1대1 메시지
- 신고 내용과 자동 제재 상태
- Wallet 잔액, Transfer 원장과 idempotency key
- 관리자 조치와 AuditLog의 무결성
- 애플리케이션 Secret Key, 가용성, 소스·설정의 기밀성

## 공격자

- 비인증 외부 사용자와 자동화 봇
- 정상 계정을 가진 악의적 사용자
- 다른 사용자의 객체 ID를 획득한 사용자
- 업로드·채팅·Socket.IO 입력을 조작하는 클라이언트
- 관리자 세션을 탈취하거나 권한 상승을 시도하는 공격자
- 과도한 요청으로 자원을 고갈시키는 공격자

## 신뢰 경계

1. 브라우저/네트워크와 Flask HTTP·Socket.IO 입력 경계
2. Flask 라우트와 인증·검증·service 계층 경계
3. 애플리케이션과 SQLite/파일 저장소 경계
4. 일반 사용자와 관리자 권한 경계
5. 개발 설정과 운영 secret/HTTPS/rate-limit 저장소 경계

클라이언트의 hidden field, sender ID, role, Content-Type, 파일명과 객체 ID는 모두 신뢰하지
않는다.

## 공격 표면

- 가입·로그인·로그아웃·프로필 폼과 세션
- 상품 CRUD와 이미지 multipart 업로드
- Socket.IO 연결, 전체 채팅과 1대1 이벤트
- 신고 생성·집계·관리자 검토
- 송금 요청, 중복 요청과 동시성
- UUID 기반 상세/변경 라우트와 관리자 UI
- 오류 페이지, health, 정적 파일, 의존성 및 migration 운영

## STRIDE 분석

| 분류 | 위협 | 영향 | 완화책 | 잔여 위험 |
|---|---|---|---|---|
| Spoofing | 로그인 우회, chat sender 위조, 세션 탈취 | 타인 행위 가장 | Flask-Login, 서버 session에서 sender 결정, Secure/HttpOnly/SameSite, 로그인 rate limit | 피싱·단말 탈취는 별도 통제 필요 |
| Tampering | 가격·잔액·role·대상 ID 조작, 중복 송금 | 재화 및 상태 무결성 훼손 | 서버 검증, 객체 권한, CHECK/FK/UNIQUE, 원자 트랜잭션, idempotency | SQLite 동시성 설계를 부하 테스트해야 함 |
| Repudiation | 관리자·송금·신고 행위 부인 | 조사/복구 곤란 | 변경 불가능한 의미의 AuditLog, actor/action/target/시간 기록 | DB 관리자 수준 변조 방지는 범위 밖 |
| Information disclosure | 평문 비밀번호, 1대1 IDOR, 스택·경로 노출 | 계정 및 사생활 침해 | scrypt, 최소 조회, 참여자 검사, 안전한 오류, CSP/헤더, 로그 비밀 금지 | metadata 노출 정책 추가 검토 |
| Denial of service | 대용량 업로드, 채팅/로그인 폭주, DB lock | 서비스 중단 | 5 MiB, endpoint/event rate limit, 짧은 트랜잭션, 운영 외부 저장소 | 단일 인스턴스 장애·분산 공격은 인프라 필요 |
| Elevation of privilege | 일반 가입자의 admin role, IDOR | 전체 서비스 장악 | 서버 고정 기본 role, admin decorator, 객체 단위 검사, CSRF, 관리자 감사 | 관리자 계정 강한 인증은 향후 필요 |

## 주요 위협과 상세 완화

| ID | 시나리오 | 계획된/현재 완화 |
|---|---|---|
| TM-01 | 유출된 고정 키로 세션 위조 | 환경 키 필수, 로컬 `.env` 비추적, 운영 key rotation 절차 예정 |
| TM-02 | 비밀번호 DB 유출 | Werkzeug 기본 scrypt, 원문 필드 금지, 최소 조회 |
| TM-03 | CSRF로 프로필·신고·송금 변경 | 전역 CSRF, 상태 변경 GET 금지, SameSite=Lax |
| TM-04 | UUID 추측/공유를 통한 IDOR | 로그인 후 객체 소유권·대화 참여자·admin role 서버 검사 |
| TM-05 | 저장 XSS와 CSP 우회 | Jinja autoescape, `safe` 금지, 서버 길이 검증, self-only CSP |
| TM-06 | 위장 파일·path traversal | Pillow decode/재생성, allowlist, 랜덤명, 고정 루트 |
| TM-07 | 신고 중복/race로 자동 제재 조작 | 복합 UNIQUE, distinct reporter 집계, 단일 트랜잭션, 관리자 복구 |
| TM-08 | 중복·동시 송금으로 잔액 음수 | 양수/상이 사용자 CHECK, balance CHECK, idempotency UNIQUE, 원자 update |
| TM-09 | Socket.IO payload가 sender/대화방 위조 | 연결·이벤트별 인증, sender session 고정, conversation 참여자 조회 |
| TM-10 | 로그에 secret/세션 유출 | AuditLog allowlist, 중앙 로깅 redaction, 오류 응답 일반화 |
| TM-11 | 취약한 dependency 공급망 | exact pin, pip-audit, 정기 업데이트와 변경 검토 |

## 잔여 위험

- Phase 01에서 업무 라우트와 Socket.IO 이벤트는 공개하지 않았으며 해당 완화책은 구현 전이다.
- SQLite는 높은 쓰기 동시성에 제한이 있어 송금과 신고 집계의 경쟁 조건 시험이 필요하다.
- memory rate-limit 저장소는 다중 프로세스/인스턴스에서 일관되지 않는다.
- 운영 HTTPS 종료, secret rotation, 백업·복구, 로그 보존, 관리자 MFA는 배포 범위에서 별도
  설계해야 한다.
- Pillow 기반 이미지 처리도 자원 고갈 가능성이 있으므로 pixel 수 제한과 처리 timeout을
  업로드 단계에서 추가한다.
