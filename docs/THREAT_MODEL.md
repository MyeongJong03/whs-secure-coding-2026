# Threat Model

## 범위와 자산

현재 공격 표면은 공개 index·health, 인증·사용자 기능, 공개 상품 목록·상세·이미지,
소유자 상품 생성·목록·수정·상태·삭제, 상품 검색, Flask session, upload filesystem과
SQLite다. 채팅·신고·송금·관리자 route와 UI는 아직 공격 표면으로 공개하지 않았다.

주요 자산은 사용자명, scrypt password hash, 인증 session, role/status/auth_version, bio,
Wallet 가상 포인트, 상품 소유권·상태·가격, 정규화 상품 이미지, application Secret Key,
filesystem과 DB 무결성이다. password 원문, session 값과 원본 upload filename은 저장·로그
대상이 아니다.

## 공격자와 신뢰 경계

- 비인증 사용자, credential stuffing 자동화 봇, 사용자 존재 여부를 수집하는 공격자
- 정상 계정으로 다른 User ID나 권한 필드를 조작하는 사용자
- 저장·반사 XSS, CSRF, SQL injection, open redirect를 시도하는 client
- 탈취·고정·오래된 session cookie를 재사용하는 공격자
- 상품 UUID, 숨겨진 form field, search/sort 문자열과 악성 upload를 조작하는 공격자

브라우저 입력, query/form의 user ID·role·status·balance, cookie의 서명 전 내용, 공개 URL의
username, product UUID, seller/status/image filename, 확장자·Content-Type과 DB image
filename은 신뢰하지 않는다. Flask form·CSRF·Limiter, route/service, Pillow/image,
filesystem, ORM/SQLite와 일반 user/admin 경계에서 다시 검증한다.

## STRIDE 요약

| 분류 | 현재 Phase 위협 | 구현된 완화 | 잔여 위험 |
|---|---|---|---|
| Spoofing | 자격 증명 대입, session fixation·재사용 | scrypt, generic login, dummy hash, login rate limit, `session.clear()`, strong protection, `auth_version` | 유출 자격 증명 자체와 피싱은 별도 통제 필요 |
| Tampering | 가입 role/status/balance 조작, 타인 bio 변경 | 허용 form 필드만 사용, 서버 고정 role/status/version/balance, 현재 session User만 변경, DB CHECK/UNIQUE | 후속 객체 route는 별도 객체 권한 필요 |
| Repudiation | 비밀번호 변경 부인 | 민감정보를 기록하지 않는 정책, transaction과 검증 테스트 | 계정 보안 이벤트 감사 설계는 후속 검토 |
| Information disclosure | 계정 열거, password/hash/UUID/잔액 노출 | 동일 실패 상태·메시지·구조, 공개 필드 `username`/`bio` allowlist, 일반 오류 | 응답 시간 완전 균등은 보장하지 않음 |
| Denial of service | scrypt 로그인·가입·검색·변경 폭주 | endpoint별 IP/사용자 rate limit, 입력·페이지 상한 | `memory://`는 다중 인스턴스에 부적합 |
| Elevation of privilege | 일반 가입으로 admin 획득 | role 입력 없음, `role=user` 명시, 임의 필드 무시, 테스트 | 관리자 기능 자체는 Phase 05까지 미구현 |

## 인증·사용자 상세 위협

| ID | 시나리오 | 구현된 완화 | 잔여 위험 |
|---|---|---|---|
| TM-01 | credential stuffing·brute force | 로그인 POST IP당 5/minute·20/hour, scrypt, 계정 영구 잠금 없음 | 분산 IP 공격은 외부 WAF·공유 limiter 필요 |
| TM-02 | 존재하지 않는 사용자·dormant 계정 enumeration | 모두 401, 같은 일반 메시지·template 구조, 없는/dormant는 앱 시작 시 만든 dummy scrypt hash 검증 | DB 조회와 실제/dummy hash의 미세 timing 차이는 완전 제거되지 않음 |
| TM-03 | 로그인 전 session fixation | 성공 직전 `session.clear()`, fresh non-remember login, permanent 8시간 session | Secret Key·TLS 운영이 잘못되면 cookie 보호 약화 |
| TM-04 | dormant session의 stale resurrection | user loader가 inactive 시 인증 키를 제거하여 재활성화 뒤에도 과거 session은 anonymous | status 변경 관리자 흐름은 Phase 05 예정 |
| TM-05 | 비밀번호 변경 뒤 다른 browser session reuse | hash와 `auth_version` 동시 commit, loader exact version 비교, 현재 browser만 새 session 수립 | 이미 진행 중인 동시 요청 처리 경계는 배포 환경에서 추가 관찰 필요 |
| TM-06 | auth_version 누락·변조 cookie | 서명된 session + 버전 존재·정확 일치 요구, mismatch 인증 키 purge | Secret Key 노출 시 서명 보호 자체가 무력화됨 |
| TM-07 | CSRF logout·profile·password 변경 | 전역 Flask-WTF CSRF, 상태 변경 POST, SameSite=Lax | XSS가 생기면 동일 origin 요청은 가능하므로 XSS 완화 병행 |
| TM-08 | 저장 XSS bio | 최대 500자, Markup/`safe` 금지, Jinja autoescape, self-only CSP | 후속 richer text 기능 추가 시 재설계 필요 |
| TM-09 | 공개 profile 과다 노출 | active 사용자만, username·bio allowlist, UUID/hash/role/status/version/balance 제외 | username·bio 자체는 의도된 공개 정보 |
| TM-10 | 사용자 검색 자원 고갈·SQL injection | q 32, page 1~1000, fixed 20, ORM binding, 60/minute | 대규모 데이터에서는 index·query plan 검토 필요 |
| TM-11 | 가입 race와 부분 생성 | 사전 중복 조회, DB UNIQUE, IntegrityError rollback, User+Wallet 단일 commit | SQLite 쓰기 경쟁은 운영 부하와 함께 검토 필요 |
| TM-12 | 오류를 통한 내부 정보 노출 | 일반 400/401/404/429/500, 500 rollback, 공통 보안 header | server-side 로그 redaction 운영 절차 필요 |

## 후속 Phase 위협

- Phase 04 채팅: Socket 인증, sender 위조, 1대1 참여자 IDOR, XSS와 spam
- Phase 05 신고·관리자: 중복/race 제재, 관리자 role, 복구 원자성, 감사 로그
- Phase 06 송금: 잔액 race, 자기·음수 송금, 멱등성, 원장 불변성

이 후속 항목은 아직 구현된 완화로 간주하지 않는다.

## Phase 03 상품·이미지·검색 위협

| ID | 위협 | 구현된 완화 | 잔여 위험 |
|---|---|---|---|
| TM-13 | Product UUID만 믿는 수정·삭제·상태 IDOR | current user owner query, 타인/없는 객체 동일 404, login/CSRF, IDOR DB-state 테스트 | 관리자 객체 권한은 Phase 05에서 별도 구현 |
| TM-14 | seller_id/status/image_filename mass assignment로 소유권·제재 우회 | 해당 form field와 service 인자 없음, 생성 owner/status 고정, 임의 POST 무시, 상태 allowlist | 신규 bulk/API 추가 시 같은 allowlist 필요 |
| TM-15 | title/description 저장 XSS | 길이 검증, Jinja autoescape, `safe`/Markup·inline script 금지, self CSP, 악성 문자열 테스트 | 미래 rich text는 별도 sanitizer 설계 필요 |
| TM-16 | q SQL injection과 sort/direction injection | ORM binding, `contains(autoescape=True)`, 완성 SQL expression dictionary, literal `%/_`와 injection-shaped query 테스트 | DB별 collation·검색 성능은 운영 데이터로 검토 |
| TM-17 | extension·Content-Type 위장과 비이미지 upload | bounded raw read, 실제 Pillow decode/verify, format-extension 일치, 허용 format만 재인코딩 | Pillow decoder 취약점은 dependency update/audit 필요 |
| TM-18 | path traversal·NUL·원본 filename 충돌과 configured upload root symlink 치환 | separator/NUL 거부, 원본명 미사용, 32 hex random, O_EXCL, web root 밖 저장, root final component lstat·directory 검사 | upload root의 parent directory가 공격자 쓰기 가능하면 이름 교체·가용성 공격의 잔여 위험이 있음 |
| TM-19 | symlink·unsafe DB filename으로 임의 파일 읽기·삭제 | exact pattern, root dir_fd 상대 stat/open/unlink, 가능한 O_NOFOLLOW, file lstat/fstat inode·regular-file·size/format 확인, 모두 일반 404 | 플랫폼에 O_NOFOLLOW가 없는 경우 명시적 inode identity 검사와 root/parent 권한에 더 의존 |
| TM-20 | GIF/APNG/WebP animation, 저장 후 큰 이미지 변조와 decompression bomb DoS | upload와 read 모두 single-frame·warning-as-error·4096 dimension·16M pixel 검사, 4 MiB input/output, request 5 MiB, rate limit | 동시 decoder CPU/memory 격리는 deployment resource limit 필요 |
| TM-21 | polyglot trailing script/ZIP 또는 metadata privacy leak | EXIF transpose 후 RGB/RGBA 새 encode, info 제거, output size 재검사, marker/metadata 자동 테스트 | encoded 픽셀 자체에 보이는 민감정보는 사용자 책임 |
| TM-22 | direct image URL로 hidden/deleted 또는 dormant seller 자료 노출 | 매 요청 DB status/seller active 확인, 비공개는 owner session만, no-store, soft delete 즉시 차단 | owner는 정책상 자기 비공개 원본의 정규화 사본을 계속 볼 수 있음 |
| TM-23 | 공개 SELECT·template context 과다 노출 | 명시 column projection, frozen slots DTO, SQL/DTO/context 검증, image URL은 Product id만 사용 | seller username은 의도된 공개 식별자 |
| TM-24 | file 저장과 DB commit 불일치 | create rollback cleanup, replacement 실패 new cleanup/old 유지, 성공 후 old 제거, soft delete file 유지 | process crash window의 고아 파일은 후속 maintenance 필요 |
| TM-25 | hidden/deleted query parameter 우회와 대량 pagination | 공개 status 조건 고정, seller active 고정, page 1~1000, fixed LIMIT 20, IP 60/minute | memory limiter는 다중 instance에 공유되지 않음 |
| TM-26 | 가격 무결성 우회 | form 1~1B integer와 named DB CHECK, 경계/직접 DB 테스트 | 통화·세금·실결제는 현재 범위가 아님 |
| TM-27 | path 검사와 open 사이 TOCTOU 또는 local filesystem 변조 | root는 resolve 없이 lstat→open→fstat의 device/inode identity를 확인하고 descriptor를 고정한다. create/read/remove 모두 그 root dir_fd 상대 접근이며 파일도 stat/open/fstat identity를 확인한다. 변조 파일은 read-time format·dimension·pixel·frame·verify를 다시 통과해야 한다. | parent나 upload directory에 공격자 쓰기 권한이 있으면 반복 치환에 의한 거부 서비스와 open 이후 unlink 대상 교체 위험이 남으므로 배포 권한 격리가 필요 |

## 운영 잔여 위험

- `memory://` limiter는 단일 프로세스 개발·시험용이다. 운영 다중 인스턴스는 공유 저장소가
  필요하다.
- HTTPS 종료, HSTS, Secret Key rotation, 백업·복구, 중앙 로그 redaction, 관리자 MFA는 배포
  범위에서 별도 검증해야 한다.
- 계정 복구, 이메일 검증, MFA는 현재 과제 범위에 없다.
- SQLite는 높은 쓰기 동시성에 한계가 있어 후속 송금·신고 transaction에서 별도 경쟁 시험이
  필요하다.
