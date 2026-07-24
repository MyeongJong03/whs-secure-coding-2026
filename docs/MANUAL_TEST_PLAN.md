# Manual Test Plan

## 목적과 실행 원칙

이 문서는 자동 구현 검토가 끝난 뒤 사람이 실제 browser 또는 독립 client session으로 수행할
최종 사용성·통합 시험 계획이다. 현재 결과는 전부 `NOT RUN`이며 실제 수행 전 성공·실패
사례나 유지보수 사건으로 기록하지 않는다.

- 실제 password, CSRF token, session cookie, raw/derived idempotency key, 내부 UUID, private
  URL과 로컬 절대경로는 캡처·보고서·로그에서 제거한다.
- 계정명, 상품, 대화와 신고 사유는 synthetic test data만 사용한다.
- browser 개발자 도구를 캡처할 때 Cookie·Authorization·form hidden token과 request body를
  숨긴다.
- 각 mutation은 화면 결과뿐 아니라 허용된 관리 화면 또는 로컬 DB 검증 절차로 상태를
  대조한다. DB 원문에 password hash·token/key를 출력하지 않는다.
- 오류가 발생하면 성공으로 바꾸지 않고 실제 현상과 재현 절차를 별도 검토한다.
- 실제 유지보수 사례가 확정되기 전에는 `MAINTENANCE_LOG.md`를 변경하지 않는다.

## 테스트 계정·역할 준비 계획

| 계정 별칭 | 역할·초기 상태 | 준비 목적 | 결과 |
|---|---|---|---|
| USER-A | 일반 user, active, Wallet 100000 | 상품·채팅·신고·송금 sender | NOT RUN |
| USER-B | 일반 user, active, Wallet 100000 | 채팅 participant·송금 recipient·신고 대상 | NOT RUN |
| USER-C | 일반 user, active, Wallet 100000 | 세 번째 participant·신고자·IDOR 검증 | NOT RUN |
| REPORTER-1~3 | 서로 다른 일반 user, active | 신고 threshold 1·2·3명 검증 | NOT RUN |
| DORMANT-U | 일반 user, dormant | 로그인·채팅·송수신 거부 검증 | NOT RUN |
| ADMIN-A | admin, active, CLI 생성 Wallet 100000 | 관리자 조회·검토·복구 | NOT RUN |

모든 계정은 재사용하지 않는 synthetic password로 준비하고 보고서에는 실제 값을 남기지
않는다. admin은 web form이나 기본 credential이 아니라 `create-admin` hidden prompt로만
준비한다.

## Browser·독립 session 준비

| 준비 ID | 준비 항목 | 절차 | 기대 결과 | 결과 |
|---|---|---|---|---|
| PREP-01 | Browser profile A/B/C | USER-A, USER-B, USER-C를 서로 격리된 profile/private window에 로그인 | cookie·CSRF·Socket 상태가 계정 사이에 공유되지 않음 | NOT RUN |
| PREP-02 | Admin browser | ADMIN-A 전용 profile에서 로그인하고 일반 user profile과 분리 | 일반 user session으로 admin URL 접근 불가 | NOT RUN |
| PREP-03 | 독립 HTTP session | 같은 test DB를 사용하는 별도 client/session을 준비 | 중복 요청·concurrency를 서로 독립된 session에서 관찰 가능 | NOT RUN |
| PREP-04 | 캡처 redaction | 주소창·개발자 도구·화면의 민감 field를 사전 점검 | cookie·token·password·내부 ID·private URL이 캡처에 없음 | NOT RUN |

## 기능별 수동 테스트

| Test ID | 기능·조건 | 계정·session | 절차 | 기대 결과 | 캡처 ID | 민감정보 제거 | 결과 |
|---|---|---|---|---|---|---|---|
| MAN-01 | 전체 채팅 정상 | USER-A/B browser | 두 사용자가 `/chat`에 접속해 각각 메시지를 전송 | 두 browser에 server sender와 message가 표시되고 새로고침 history 유지 | FIG-27 | body는 synthetic, cookie·CSRF·sid 제외 | NOT RUN |
| MAN-02 | 1대1 채팅 정상 | USER-A/B browser | USER-A가 USER-B와 대화를 시작하고 양방향 전송 | 두 participant만 같은 canonical conversation history·live message 확인 | FIG-28 | conversation UUID·cookie·sid 제외 | NOT RUN |
| MAN-03 | 1대1 채팅 제3자 차단 | USER-C browser | USER-A/B conversation URL에 직접 접근 | missing과 구분되지 않는 404 또는 일반 오류 | FIG-29 | 실제 UUID 대신 synthetic/crop, session 제외 | NOT RUN |
| MAN-04 | 신고 1·2명 | REPORTER-1/2 | 같은 active 일반 사용자 또는 상품을 각각 신고 | 신고는 저장되지만 대상 상태는 active 또는 기존 sold 유지 | 해당 없음 | reason 원문 최소화, 내부 target ID 제외 | NOT RUN |
| MAN-05 | 신고 세 번째 threshold | REPORTER-3 | 같은 대상에 세 번째 유효 신고 | 일반 user는 dormant 또는 상품은 hidden, system audit 생성 | FIG-36/FIG-37 | reporter 계정·reason·version·sid 제외 | NOT RUN |
| MAN-06 | 관리자 신고 검토 | ADMIN-A | pending 신고를 current password와 CSRF POST로 confirm/reject | reviewer/time/status와 audit가 함께 반영 | FIG-38 | current password·CSRF·내부 ID 제외 | NOT RUN |
| MAN-07 | 관리자 사용자 복구 | ADMIN-A, 제한 대상 user | dormant 일반 사용자를 active로 복구하고 과거/새 login 비교 | 과거 session은 계속 무효이고 새 login만 성공 | FIG-39 | password·cookie·auth_version 제외 | NOT RUN |
| MAN-08 | 관리자 상품 복구 | ADMIN-A | 자동 hidden 상품을 복구 | 직전 active/sold 정책 상태로 복구되고 row/image 유지 | FIG-40 | image filename·seller ID 제외 | NOT RUN |
| MAN-09 | 송금 전 Wallet 확인 | USER-A/B | 각 `/wallet`에서 초기 balance와 고지 확인 | 두 계정 balance 100000, 실제 금융 자산 아님 문구 표시 | FIG-45 | cookie·내부 user ID 제외 | NOT RUN |
| MAN-10 | 정상 송금 | USER-A→USER-B | transfer GET 후 recipient username, amount와 current password로 POST | 성공 detail로 303, 한 Transfer만 생성 | FIG-46 | password·hidden token·내부 ID 제외 | NOT RUN |
| MAN-11 | 송금 후 양쪽 잔액 | USER-A/B | 정상 송금 뒤 각 `/wallet` 새로고침 | sender는 정확히 차감, recipient는 정확히 증가, 총합 불변 | FIG-47 | synthetic username 외 식별정보 제외 | NOT RUN |
| MAN-12 | 잔액 초과 거부 | USER-A | 현재 balance보다 큰 정수 송금 | 일반 오류, 양쪽 balance와 history 불변 | FIG-48 | password·token·DB 오류 정보 제외 | NOT RUN |
| MAN-13 | 자기 송금 거부 | USER-A | recipient에 자기 username 입력 | 일반 오류, balance·Transfer·AuditLog 불변 | FIG-49 | password·token 제외 | NOT RUN |
| MAN-14 | dormant recipient 거부 | USER-A→DORMANT-U | dormant username으로 송금 | 없는 사용자와 구분되지 않는 unavailable 오류, 상태 불변 | 해당 없음 | 대상 실제 상태·내부 ID 제외 | NOT RUN |
| MAN-15 | wrong current password | USER-A→USER-B | 잘못된 current password로 정상 형식 송금 | 일반 재확인 오류, password 미반사, 상태 불변 | 해당 없음 | 입력 password 자체를 캡처하지 않음 | NOT RUN |
| MAN-16 | 중복 요청 한 번 처리 | USER-A→USER-B, 독립 session | 같은 form 요청을 재전송하되 hidden token을 화면·로그에 노출하지 않음 | 같은 detail 결과, debit·credit·Transfer·audit 각각 한 번 | FIG-50 | raw/derived token/key와 request body 제외 | NOT RUN |
| MAN-17 | idempotency mismatch | USER-A, 독립 session | 같은 요청 token을 다른 amount 또는 recipient로 재전송하는 통제된 검증 | 409 conflict 또는 안전한 오류, balance·원장 불변 | 해당 없음 | token/key 자체를 캡처·기록하지 않음 | NOT RUN |
| MAN-18 | 송금 이력 filter | USER-A/B | all/sent/received와 newest/oldest, pagination을 전환 | 본인 participant row만 보이고 filter가 page link에 유지 | FIG-51 | 타 사용자·내부 ID·key 제외 | NOT RUN |
| MAN-19 | 송금 detail IDOR | USER-C | USER-A/B Transfer detail URL 직접 접근과 무작위 missing 비교 | 두 요청 모두 같은 404 | 해당 없음 | Transfer UUID·private URL 제외 | NOT RUN |
| MAN-20 | 관리자 Transfer 조회 | ADMIN-A | `/admin/transfers`에서 MAN-10 송금 검색·정렬 확인 | 원장 Transfer ID·sender/recipient username·amount·time 표시, mutation control 없음 | FIG-52 | idempotency key·내부 user ID 제외 | NOT RUN |
| MAN-21 | Transfer 감사 로그 | ADMIN-A | action `transfer.created`, target type `transfer`로 filter | actor·action·target과 amount-only details 표시 | FIG-53 | recipient·balance·password·token/key 제외 | NOT RUN |
| MAN-22 | 일반 user 관리자 차단 | USER-A | `/admin/transfers`, `/admin/audit-logs` 직접 접근 | 403 또는 login 정책에 따른 차단 | FIG-43 | 계정·private URL 제외 | NOT RUN |
| MAN-23 | 전체 자동 검증 캡처 | 로컬 검증 terminal | 전체 pytest와 coverage fail-under 명령 실행 | 실제 test 수와 app coverage를 사실대로 기록 | FIG-54 | 사용자 경로·환경값 crop/redact | NOT RUN |
| MAN-24 | GitHub Actions 캡처 | public repository Actions | 최종 branch의 push/PR workflow 확인 | Python 3.12 test·security·migration job 모두 실제 성공 | FIG-55 | actor 개인정보·secret·runner path 제외 | NOT RUN |

## 결과 기록

실행자는 각 행의 `NOT RUN`을 실제 `PASS` 또는 `FAIL`로만 변경하고 실행 일시, browser/version,
재현 단계와 캡처 ID를 최종 보고서에 연결한다. `FAIL`은 삭제하거나 성공으로 완화하지 않고
원인을 검토한다. 실제 사용성 결함이 재현·수정·회귀 검증된 뒤에만 별도 유지보수 사례 등록을
검토한다.
