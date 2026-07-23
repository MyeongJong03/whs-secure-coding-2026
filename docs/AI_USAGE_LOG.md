# AI Usage Log

## 사용 내역

| 도구 | 수행한 작업 | 프롬프트 목적 | 출력 검토 방식 |
|---|---|---|---|
| ChatGPT | 과제 단계 계획 및 요구사항 정리 지원 | 범위, 보안 정책, 산출물과 수용 기준 구조화 | 공식 과제 지시와 항목별 대조 후 사람이 채택 여부 결정 |
| Codex CLI | 기준선 커밋의 정적 분석 | 기존 보안 약점과 교체 대상 식별 | 기준선 파일과 Git 이력을 직접 재확인하고 Finding 근거 기록 |
| Codex CLI | Phase 01 구현 및 테스트 지원 | factory, 설정, model, migration, 문서와 자동 테스트 작성 | diff 검토, 빈 DB migration, pytest와 보안/품질 도구로 검증 |
| Codex CLI | Phase 02 인증·사용자 기능 구현 및 테스트 지원 | 가입·로그인·POST 로그아웃, 사용자 조회, 마이페이지, `auth_version`, migration, 문서와 자동 테스트 작성 | 사람이 diff를 검토하고 실제 pytest·coverage·Ruff·Bandit·pip-audit·Alembic 명령으로 확인 |
| Codex CLI | Phase 02 사람 검토 후 공개 데이터 최소화 수정과 회귀 테스트 지원 | 공개 SELECT projection·view DTO, password confirmation 길이 경계, 관련 문서 정합성 보완 | 사람이 diff와 SQL projection test를 검토하고 전체 품질·보안·migration 명령으로 재검증 |
| Codex CLI | Phase 03 상품·이미지·검색 구현 및 테스트 지원 | 상품 CRUD·소유권, 공개 projection DTO, allowlisted 검색, 안전한 이미지 decode·재인코딩·filesystem/DB coordination, 세 번째 migration과 문서 작성 | 사람이 diff·filesystem mode/state·DB schema/state·실제 SQL·HTTP status/header/body를 검토하고 pytest·coverage·정적·의존성·Alembic 명령으로 확인 |
| Codex CLI | Phase 03 사람 최종 검토 후 filesystem root hardening과 README 재현성 수정 지원 | upload root lstat/open/fstat·dir_fd 상대 이미지 접근, read-time 제한 재검증, 비밀값을 출력하지 않는 `.env` bootstrap, 회귀 테스트와 보안 문서 정합성 보완 | 검토 지적과 diff를 대조하고 filesystem target 불변·CLI 출력·전체 pytest/coverage·정적·의존성·Alembic 명령의 실제 결과로 확인 |

## 원칙

- AI 출력은 제안 또는 초안이며 사실·코드·버전·테스트 결과를 사람이 최종 검증한다.
- 성공 여부는 실제 명령 결과로만 판단하고 실패·경고를 제거하거나 숨기지 않는다.
- AI가 생성한 보안 설계도 요구사항 추적, 코드 review와 회귀 테스트를 거쳐야 한다.
- 파일·DB·HTTP 결과는 최종 HTML 문자열만으로 판단하지 않고 각각의 상태를 함께 검토한다.
- prompt나 산출물에 실제 비밀번호, Secret Key, token, session 값을 포함하지 않는다.
