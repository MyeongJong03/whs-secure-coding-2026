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
