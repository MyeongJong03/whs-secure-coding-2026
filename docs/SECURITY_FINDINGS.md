# Security Findings

## 기준선과 상태 기준

- 기준 커밋: `f0dd4baac057f62315bb4850f05d18b7e60eb4be`
- SEC-01~17 근거는 해당 커밋의 `app.py`, `templates/`, `enviroments.yaml`을 직접 정적
  분석한 실제 줄 번호다. SEC-18은 `phase-01-foundation` 태그의 `app/__init__.py` user
  loader를 개발 중 재검토해 발견했다.
- 심각도는 악용 가능성과 기밀성·무결성·가용성 영향을 기준으로 High 또는 Medium을 사용한다.
- 현재 상태는 `Mitigated`, `Partial`, `Open` 중 하나만 사용한다. `Mitigated`는 현재 Phase
  범위에서 기준선 공격 표면이 제거되고 검증 경로가 있는 경우, `Partial`은 기반만 있고 후속
  업무 제어가 남은 경우, `Open`은 유효한 완화가 아직 없는 경우다.
- 관련 commit hash는 문서가 포함되는 commit 안에 자기참조로 쓰지 않는다. 최종 보고서 생성
  단계에서 해당 시점의 Git 이력을 조회해 Finding별 관련 commit을 기록한다.

| ID | 기준선 근거 | 심각도 | 실제 영향 | 현재 완화 및 남은 범위 | 현재 상태 | 검증 방법 |
|---|---|---|---|---|---|---|
| SEC-01 | `app.py:7` | High | 공개된 고정 Secret Key로 세션 서명 위조와 계정 가장 가능 | Development·Production에서 누락·짧은 값·예제 placeholder·legacy 값을 거부하고 환경의 32자 이상 임의 키만 허용 | Mitigated | 설정별 시작 실패/성공 테스트, 추적 파일 secret 검사 |
| SEC-02 | `app.py:81-82`, `app.py:96` | High | 평문 비밀번호 저장·직접 비교로 DB 유출 시 모든 자격 증명 노출 | `password_hash`만 저장하고 가입·비밀번호 변경 모두 Werkzeug 기본 scrypt를 사용한다. 같은 비밀번호의 salt/hash 차이, 기존·새 비밀번호 로그인을 재검증했다. | Mitigated | 모델·가입·비밀번호 변경 hash 테스트 |
| SEC-03 | `app.py:210` | High | 외부 debug 실행 시 debugger·스택·환경 정보 노출 | debug 기본 false, 설정에서만 선택하고 공통 오류 handler로 내부 정보 차단 | Mitigated | 설정·source review, 404/500 응답 테스트 |
| SEC-04 | `templates/register.html:5`, `templates/profile.html:6`, `app.py:108` | High | 가입·프로필 변경·GET 로그아웃을 사용자 의사 없이 유도 가능 | 가입·로그인·소개글·비밀번호·POST 로그아웃에 전역 CSRF를 적용하고 GET 로그아웃은 405다. 미구현 상품·채팅·신고·송금 상태 변경은 후속 Phase 검증이 남았다. | Partial | Testing CSRF 활성, 각 POST token 누락 400, GET logout 405 테스트 |
| SEC-05 | `app.py:203` | High | 비인증 사용자가 Socket.IO 이벤트를 호출해 채팅 전송 가능 | 취약 이벤트와 채팅 라우트를 제거했으며 재도입 시 연결·이벤트마다 active 인증을 적용 | Mitigated | 현재 handler 부재 검토, 후속 비인증 connect/emit 거부 테스트 |
| SEC-06 | `templates/dashboard.html:39`, `app.py:204` | High | client 제공 username으로 다른 발신자를 가장해 메시지 전송 가능 | 취약 UI와 handler를 제거했으며 재도입 시 sender를 서버 세션에서만 결정 | Mitigated | 현재 공격 표면 부재 검토, 후속 sender 위조 무시 테스트 |
| SEC-07 | `app.py:204` | Medium | 메시지 형식·길이 제한 부재로 저장 XSS, spam, 자원 고갈 위험 | DB body 1~500자 CHECK만 존재하며 event 검증·escape·rate limit은 Phase 04에 필요 | Partial | DB CHECK와 후속 event 경계/rate 테스트 |
| SEC-08 | `app.py:70`, `app.py:136`, `app.py:187` | High | 가입·프로필·신고 입력의 무제한 값으로 데이터 오염, XSS와 자원 남용 가능 | Phase 02 가입·로그인·사용자 검색·bio·password 입력은 WTForms와 DB 제약으로 검증하고 bio autoescape를 시험했다. 상품·채팅·신고 입력은 아직 미구현이다. | Partial | 인증·사용자 HTTP 경계/XSS 테스트, 후속 route 테스트 예정 |
| SEC-09 | `app.py:49`, `app.py:188` | High | 신고 대상 type·존재·중복·자기 대상 미검사로 허위 신고와 자동 제재 조작 가능 | reporter/type/target UNIQUE와 target type CHECK는 구현, 대상·소유권·3명 집계 service는 후속 구현 필요 | Partial | DB 중복 테스트와 후속 존재/자기 대상/race/집계 테스트 |
| SEC-10 | `app.py:31-57` | High | FK/CHECK/NOT NULL/업무 UNIQUE 부재로 고아·음수·중복·잘못된 상태 저장 가능 | SQLAlchemy foundation 모델, SQLite foreign key PRAGMA, CHECK/UNIQUE/NOT NULL과 최초 migration 적용 | Mitigated | IntegrityError 테스트, migration upgrade/check |
| SEC-11 | `app.py:6`, `app.py:98` | Medium | 세션 쿠키 보호·만료 정책 부재로 탈취·고정·장기 재사용 위험 | HttpOnly, SameSite=Lax, 8시간 permanent session, 운영 Secure, strong protection, 로그인 `session.clear()`, fresh non-remember login과 password 변경 `auth_version` 회전을 구현했다. | Mitigated | cookie/config, fixation marker 제거, remember 부재, 버전 mismatch·다중 client 테스트 |
| SEC-12 | `app.py:89`, `app.py:182` | Medium | 로그인과 신고 요청 반복으로 brute force·spam·가용성 저하 가능 | 로그인 5/minute·20/hour, 가입 5/hour, 사용자 검색 60/minute, bio 30/hour, password 5/hour를 구현했다. 신고·채팅 rate limit은 해당 기능과 함께 남아 있다. | Partial | Phase 02 endpoint 429 임계치 테스트, 후속 신고·event 테스트 예정 |
| SEC-13 | `app.py:70`, `app.py:204` | Medium | 처리되지 않은 입력·이벤트 오류가 stack·경로·내부 상태를 노출할 수 있음 | 400/403/404/429/500 공통 handler와 500 rollback 적용, 취약 Socket event 제거 | Mitigated | 404/500 응답 내용 테스트 |
| SEC-14 | `templates/base.html:3`, `app.py:6` | Medium | 보안 응답 header 부재로 clickjacking, MIME sniffing과 XSS 영향 증가 | 중앙 after-request에서 CSP, nosniff, DENY, referrer와 permissions 정책 적용 | Mitigated | 정상·오류 응답 header 테스트 |
| SEC-15 | `enviroments.yaml:5-10`, `templates/base.html:7` | Medium | 버전 미고정 의존성과 외부 CDN 공급망으로 재현성 저하·악성 자산 노출 가능 | runtime/dev 의존성 exact pin, pip-audit, 프런트 자산 저장소 내부 제공 | Mitigated | 두 requirements 파일 audit와 template/source review |
| SEC-16 | `app.py:208-210` | Medium | 직접 실행에서만 스키마를 생성해 WSGI 기동 시 누락과 schema drift 발생 가능 | 최초 Alembic migration과 명시적 upgrade 절차로 교체 | Mitigated | 임시 빈 DB migration upgrade와 `flask db check` |
| SEC-17 | `app.py:122`, `app.py:142`, `app.py:178` | Medium | `SELECT *`로 비밀번호 등 불필요한 사용자 필드를 조회·전달해 노출 범위 증가 | 공개 목록 page query와 profile query의 SELECT 절은 `username`, `bio`만 projection한다. 전체 User ORM 객체 대신 frozen·slots `PublicUserView`와 `PublicUserPage`만 공개 template context에 전달하며 UUID·hash·role·status·version·balance 노출을 금지했다. | Mitigated | 실제 SQL SELECT projection, DTO field allowlist, route template context와 응답 금지 필드 자동 테스트 |
| SEC-18 | `phase-01-foundation:app/__init__.py` user loader | Medium | dormant User는 `None`이었지만 인증 session key가 남아 관리자가 다시 active로 바꾸면 과거 session cookie가 다시 인증될 수 있었다. 비밀번호 변경 뒤 다른 session을 구분할 버전도 없었다. | `User.auth_version`, 로그인 session 버전 저장, loader의 active·exact version 확인과 인증 키 purge를 구현했다. dormant로 anonymous가 된 뒤 active로 복구해도 과거 session은 계속 anonymous이며 password 변경은 다른 client를 무효화한다. | Mitigated | dormant 기존 session 차단, 재활성화 후 부활 방지, version 누락·mismatch, password 변경 후 다른 client 차단 자동 테스트 |

## 종결 및 추적 원칙

현재 `Partial`인 항목은 대응 업무 route나 service가 구현될 때 요구사항 ID, 자동 테스트,
migration 또는 설정 검증과 함께 재평가한다. 최종 보고서는 Git 이력에서 실제 관련 commit을
조회해 SEC-18을 포함한 Finding별 관련 commit hash를 연결하며, 검증 실패나 미구현 범위를
`Mitigated`로 변경하지 않는다. SEC-18은 자동 테스트 통과를 확인한 뒤 `Mitigated`로 갱신했다.
