# Evidence Plan

이 문서는 최종 보고서용 캡처 계획만 정의한다. 이 작업에서는 이미지 파일을 생성하거나 외부
이미지를 다운로드하지 않는다.

| FIG ID | 필요한 캡처 | 준비 상태 | 파일명 | 보고서 삽입 위치 | 캡션 | 민감정보 제거 주의사항 |
|---|---|---|---|---|---|---|
| FIG-01 | 기준선과 작업 branch/태그 | 캡처 필요 | `fig-01-baseline.png` | 배경/기준선 | 기준 commit과 보존 tag | remote URL·사용자 경로 가림 |
| FIG-02 | 프로젝트 디렉터리 구조 | 캡처 필요 | `fig-02-structure.png` | 설계 | Phase 01 factory 구조 | `.env`, 로컬 경로 제외 |
| FIG-03 | index 화면 | 캡처 필요 | `fig-03-index.png` | 구현 결과 | 공개 index | 주소창의 private host 제거 |
| FIG-04 | health JSON | 캡처 필요 | `fig-04-health.png` | 구현 결과 | health 정상 응답 | private URL 제거 |
| FIG-05 | 안전한 404/500 화면 | 캡처 필요 | `fig-05-errors.png` | 보안 검증 | 내부 정보 없는 오류 응답 | stack·경로가 우연히 노출되지 않았는지 확인 |
| FIG-06 | pytest 및 coverage 요약 | 캡처 필요 | `fig-06-tests.png` | 테스트 | 자동 테스트와 coverage | 사용자명·절대 경로 crop/redact |
| FIG-07 | Ruff/Bandit/pip-audit 결과 | 캡처 필요 | `fig-07-security-tools.png` | 보안 검증 | 정적/의존성 검사 결과 | 환경 경로·index URL 제거 |
| FIG-08 | 빈 DB migration upgrade | 캡처 필요 | `fig-08-migration.png` | DB 설계 | 최초 migration 적용 | DB 절대 경로 제거 |
| FIG-09 | 보안 header 확인 | 캡처 필요 | `fig-09-headers.png` | 위협 완화 | CSP와 공통 보안 header | cookie 값·SECRET 절대 포함 금지 |
| FIG-10 | 최종 Git 변경 목록 | 캡처 필요 | `fig-10-git-status.png` | 변경 내역 | commit 전 working tree | remote, 개인 경로, `.env` 내용 제외 |
| FIG-11 | 회원가입 화면 | 캡처 필요 | `fig-11-register.png` | Phase 02 구현 | 입력 정책과 CSRF form | 실제 password·cookie 값 제외 |
| FIG-12 | 로그인 화면 | 캡처 필요 | `fig-12-login.png` | Phase 02 구현 | 일반 로그인 화면 | 자격 증명·cookie 값 제외 |
| FIG-13 | 사용자 검색 | 캡처 필요 | `fig-13-user-search.png` | Phase 02 구현 | active 사용자 검색과 pagination | 내부 UUID·비공개 field가 없는지 확인 |
| FIG-14 | 공개 프로필 | 캡처 필요 | `fig-14-public-profile.png` | Phase 02 구현 | username·bio 공개 allowlist | hash·role·status·balance 제외 |
| FIG-15 | 마이페이지 | 캡처 필요 | `fig-15-me.png` | Phase 02 구현 | 본인 bio·가상 포인트와 금융 자산 아님 안내 | session·UUID 제외 |
| FIG-16 | 비밀번호 변경과 다른 세션 무효화 | 캡처 필요 | `fig-16-password-session.png` | Phase 02 보안 검증 | 현재 client 유지·과거 client anonymous | password·hash·cookie·auth_version 원문 제외 |
| FIG-17 | Phase 02 pytest 요약 | 캡처 필요 | `fig-17-phase02-pytest.png` | 테스트 | 테스트 수와 app coverage | 절대경로·환경 정보 crop/redact |
| FIG-18 | 공개 상품 목록 | 캡처 필요 | `fig-18-products.png` | Phase 03 구현 | active/sold 상품과 이미지 | 내부 UUID·저장 filename·private URL 제외 |
| FIG-19 | 상품 등록과 이미지 | 캡처 필요 | `fig-19-product-create.png` | Phase 03 구현 | 필수 입력과 안전 이미지 등록 | 원본 filename·로컬 경로·cookie 제외 |
| FIG-20 | 공개 상품 상세 | 캡처 필요 | `fig-20-product-detail.png` | Phase 03 구현 | 상품과 판매자 username 최소 공개 | seller UUID·hash·role·filename 제외 |
| FIG-21 | 내 상품 관리 | 캡처 필요 | `fig-21-my-products.png` | Phase 03 구현 | 모든 본인 상태와 수정·삭제 form | 다른 사용자 정보·cookie 제외 |
| FIG-22 | 판매 완료 전환 | 캡처 필요 | `fig-22-product-sold.png` | Phase 03 구현 | active에서 sold POST 전환 | CSRF token·session 제외 |
| FIG-23 | 검색·가격·정렬 | 캡처 필요 | `fig-23-product-search.png` | Phase 03 구현 | q/status/price/sort/pagination | private URL·개인 경로 제외 |
| FIG-24 | 타 사용자 수정 차단 | 캡처 필요 | `fig-24-product-idor.png` | Phase 03 보안 | 타인과 없는 상품 동일 404 | 실제 계정·UUID는 테스트 값만 사용 |
| FIG-25 | 위험 이미지 거부 | 캡처 필요 | `fig-25-image-rejected.png` | Phase 03 보안 | 일반 upload 오류 화면 | 공격 filename·path·exception 비노출 확인 |
| FIG-26 | Phase 03 pytest 결과 | 캡처 필요 | `fig-26-phase03-pytest.png` | 테스트 | 전체 테스트 수와 현재 app coverage | 절대경로·환경 정보 crop/redact |
| FIG-27 | 두 browser의 전체 실시간 채팅 | 캡처 필요 | `fig-27-global-chat.png` | Phase 04 구현 | 두 active 사용자의 global message 동시 수신 | cookie·CSRF·sid·내부 UUID 제외 |
| FIG-28 | 두 participant의 1대1 채팅 | 캡처 필요 | `fig-28-direct-chat.png` | Phase 04 구현 | canonical direct room의 양방향 message | conversation URL UUID와 계정은 synthetic 값만 사용 |
| FIG-29 | 제3자 direct 접근 차단 | 캡처 필요 | `fig-29-direct-idor.png` | Phase 04 보안 | nonparticipant와 missing의 동일 404 또는 generic 오류 | 실제 계정·private URL 제외 |
| FIG-30 | sender 위조 payload 차단 | 캡처 필요 | `fig-30-sender-spoof.png` | Phase 04 보안 | client sender field 거부와 server sender 유지 | payload에 token·cookie·sid를 넣지 않음 |
| FIG-31 | logout·password 변경 뒤 Socket 종료 | 캡처 필요 | `fig-31-stale-socket.png` | Phase 04 보안 | HTTP auth lifecycle 직후 old connection 종료 | password·hash·auth_version·session 값 제외 |
| FIG-32 | message event rate limit | 캡처 필요 | `fig-32-chat-rate-limit.png` | Phase 04 보안 | user 합산 burst 제한의 generic 안내 | 내부 user ID·body 원문·sid 제외 |
| FIG-33 | Phase 04 pytest·coverage 결과 | 캡처 필요 | `fig-33-phase04-pytest.png` | 테스트 | 기존 307 회귀를 포함한 전체 수와 app coverage | 절대경로·환경 정보 crop/redact |
| FIG-34 | 사용자 신고 작성 | 캡처 필요 | `fig-34-user-report.png` | Phase 05 구현 | 다른 active 사용자 reason-only 신고 form | CSRF·내부 UUID·cookie 제외 |
| FIG-35 | 상품 신고 작성 | 캡처 필요 | `fig-35-product-report.png` | Phase 05 구현 | 다른 사용자의 active/sold 상품 신고 form | seller/target 내부 ID 제외 |
| FIG-36 | 세 번째 신고 뒤 상품 hidden | 캡처 필요 | `fig-36-auto-product-hidden.png` | Phase 05 자동 제재 | 서로 다른 세 신고 뒤 공개 목록·상세 제외 | 신고자 실제 계정·reason 원문 최소화 |
| FIG-37 | 세 번째 신고 뒤 사용자 dormant | 캡처 필요 | `fig-37-auto-user-dormant.png` | Phase 05 자동 제재 | 일반 사용자 session·Socket 즉시 무효 | cookie·version·sid 제외 |
| FIG-38 | 관리자 신고 검토 | 캡처 필요 | `fig-38-admin-report-review.png` | Phase 05 관리자 | pending 신고 confirm/reject와 reviewer | current password·CSRF 제외 |
| FIG-39 | 관리자 사용자 복구 | 캡처 필요 | `fig-39-admin-user-restore.png` | Phase 05 관리자 | dormant→active 복구와 새 로그인 요구 | password·hash·version 제외 |
| FIG-40 | 관리자 상품 복구 | 캡처 필요 | `fig-40-admin-product-restore.png` | Phase 05 관리자 | hidden 상품의 active/sold 복구 상태 | image filename·seller ID 제외 |
| FIG-41 | 관리자 message hide | 캡처 필요 | `fig-41-admin-message-hide.png` | Phase 05 관리자 | 향후 history 제외와 복구 조치 | participant ID·room·sid 제외 |
| FIG-42 | 관리자 audit log | 캡처 필요 | `fig-42-admin-audit.png` | Phase 05 감사 | actor/system, action, allowlisted details | token·session·reason·password 제외 |
| FIG-43 | 일반 사용자의 관리자 접근 차단 | 캡처 필요 | `fig-43-admin-denied.png` | Phase 05 권한 | 직접 `/admin` 접근 403 | 실제 계정·private URL 제외 |
| FIG-44 | Phase 05 pytest·coverage 결과 | 캡처 필요 | `fig-44-phase05-pytest.png` | 테스트 | 기존 408 회귀 포함 전체 수와 app coverage | 절대경로·환경 정보 crop/redact |
| FIG-45 | 송금 전 양쪽 Wallet 잔액 | 캡처 필요 | `fig-45-wallet-before.png` | Phase 06 송금 | 과제용 가상 포인트 고지와 송금 전 sender/recipient 잔액 | 내부 user ID·cookie·CSRF·token 제외 |
| FIG-46 | 정상 송금 작성과 성공 상세 | 캡처 필요 | `fig-46-transfer-success.png` | Phase 06 송금 | current password 재확인 뒤 정상 송금과 detail 303 결과 | password·hidden token·내부 Transfer/user ID 제외 |
| FIG-47 | 송금 후 양쪽 Wallet 잔액 | 캡처 필요 | `fig-47-wallet-after.png` | Phase 06 원자성 | sender 정확한 차감과 recipient 정확한 증가 | 계정은 synthetic 값만 사용하고 cookie·UUID 제외 |
| FIG-48 | 잔액 초과 송금 거부 | 캡처 필요 | `fig-48-transfer-insufficient.png` | Phase 06 실패 처리 | 일반 오류와 양쪽 잔액·원장 불변 | 실제 password·balance 외 민감 내부 상태 제외 |
| FIG-49 | 자기 송금 거부 | 캡처 필요 | `fig-49-transfer-self.png` | Phase 06 입력 정책 | 자기 username 송금의 일반 거부 | password·token·내부 user ID 제외 |
| FIG-50 | 중복 요청 한 번 처리 | 캡처 필요 | `fig-50-transfer-idempotent.png` | Phase 06 멱등성 | 동일 요청 재전송 뒤 같은 detail과 1회 debit/credit | raw/derived idempotency token/key를 캡처하지 않음 |
| FIG-51 | 사용자 송금 이력과 방향 filter | 캡처 필요 | `fig-51-transfer-history.png` | Phase 06 조회 | sent/received/all과 fixed pagination | participant 외 계정·내부 ID·key 제외 |
| FIG-52 | 관리자 Transfer 읽기 전용 조회 | 캡처 필요 | `fig-52-admin-transfers.png` | Phase 06 관리자 통합 | 실제 송금의 최소 projection과 mutation 부재 | idempotency key·sender/recipient 내부 ID 제외 |
| FIG-53 | transfer.created 감사 로그 | 캡처 필요 | `fig-53-transfer-audit.png` | Phase 06 감사 | actor/action/target과 amount-only details | recipient·balance·password·token/key 제외 |
| FIG-54 | Phase 06 전체 pytest·coverage | 캡처 필요 | `fig-54-phase06-pytest.png` | 최종 테스트 | 기존 518 회귀 포함 전체 test 수와 현재 app coverage | 절대경로·환경 정보 crop/redact |
| FIG-55 | GitHub Actions 성공 | 캡처 필요 | `fig-55-github-actions.png` | 최종 CI | Python 3.12 테스트·보안·migration job 성공 | repository secret·runner 내부 경로·actor 개인정보 제외 |
