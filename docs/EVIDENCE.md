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
