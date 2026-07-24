# Threat Model

## 범위와 자산

현재 공격 표면은 공개 index·health, 인증·사용자 기능, 공개 상품 목록·상세·이미지,
소유자 상품 생성·목록·수정·상태·삭제, 상품 검색, Flask session, upload filesystem과
SQLite, `/chat` HTTP와 `/chat` Socket.IO namespace, 신고·자동 제재, 관리자 read/mutation,
감사 로그, Wallet 요약·송금·사용자 이력·상세와 관리자 Transfer read-only UI다.

주요 자산은 사용자명, scrypt password hash, 인증 session, role/status/auth_version, bio,
Wallet 가상 포인트, 상품 소유권·상태·가격, 정규화 상품 이미지, application Secret Key,
전체·1대1 message와 대화 참여 관계, Socket CSRF·연결 registry, 신고·제재·감사 이력,
Transfer 원장과 sender/recipient 관계, filesystem과 DB 무결성이다. password 원문,
session/CSRF/sid 값, raw/derived idempotency key와 원본 upload filename은 일반
저장·로그·응답 대상이 아니다. Transfer의 derived key만 DB UNIQUE 예약용으로 저장한다.

## 공격자와 신뢰 경계

- 비인증 사용자, credential stuffing 자동화 봇, 사용자 존재 여부를 수집하는 공격자
- 정상 계정으로 다른 User ID나 권한 필드를 조작하는 사용자
- 저장·반사 XSS, CSRF, SQL injection, open redirect를 시도하는 client
- 탈취·고정·오래된 session cookie를 재사용하는 공격자
- 상품 UUID, 숨겨진 form field, search/sort 문자열과 악성 upload를 조작하는 공격자
- cross-site Socket 연결, sender/conversation/room payload, oversized packet과 다중 sid로
  인증·권한·quota를 우회하려는 공격자
- sender/recipient ID, balance, amount, recipient username, raw/derived idempotency key와
  Transfer UUID를 조작해 이중 지출·중복 송금·타인 이력 접근을 시도하는 사용자
- 열린 browser, 탈취한 현재 비밀번호 또는 재전송된 form을 이용해 송금을 시도하는 공격자

브라우저 입력, query/form의 user ID·role·status·balance, cookie의 서명 전 내용, 공개 URL의
username, product UUID, seller/status/image filename, 확장자·Content-Type과 DB image
filename, Socket username/user ID/sender ID/auth version/room name, 송금 sender/recipient ID,
amount와 idempotency token/key는 신뢰하지 않는다. sender는 current authenticated user,
recipient는 username server lookup으로 결정한다. Flask form·CSRF·Limiter, Socket
connect/event decorator·registry, route/service, password verifier, Pillow/image, filesystem,
ORM/SQLite와 일반 user/admin 경계에서 다시 검증한다.

## STRIDE 요약

| 분류 | 현재 Phase 위협 | 구현된 완화 | 잔여 위험 |
|---|---|---|---|
| Spoofing | 자격 증명 대입, session/Socket 재사용, message/transfer sender 위조 | scrypt, generic login, `auth_version`, CSRF, current password, server-derived sender와 event 재인증 | 유출 자격 증명·현재 비밀번호 자체와 피싱은 별도 통제 필요 |
| Tampering | 권한·잔액·recipient·amount·idempotency 조작과 타인 객체 접근 | 허용 form 필드, current user/participant query, 조건부 debit, DB CHECK/UNIQUE/FK, 원자 transaction | DB 직접 쓰기 권한을 가진 운영자는 별도 통제 필요 |
| Repudiation | 관리자 조치·송금 부인 또는 audit 누락 | 업무 변경과 allowlisted AuditLog를 같은 transaction으로 처리 | 외부 append-only audit와 계정 보안 이벤트 감사는 배포 범위 |
| Information disclosure | hash/UUID/잔액·제3자 message/transfer·token/key 노출 | 동일 오류, 최소 projection DTO, participant query, raw token 비저장·key 미표시 | 의도된 counterpart username과 amount는 participant에게 공개 |
| Denial of service | scrypt·검색·Socket·신고·송금 폭주와 SQLite write contention | endpoint/event user limit, bounded 입력/page/connection, busy timeout, 짧은 transaction | memory limiter와 SQLite는 다중 인스턴스·고 write 부하에 부적합 |
| Elevation of privilege | 일반 가입의 admin 획득, admin/Transfer IDOR | role 입력 없음, CLI-only admin, active RBAC, route-derived target, participant query, admin read-only Transfer | admin 계정 탈취와 운영 DB 권한은 별도 통제 필요 |

## 인증·사용자 상세 위협

| ID | 시나리오 | 구현된 완화 | 잔여 위험 |
|---|---|---|---|
| TM-01 | credential stuffing·brute force | 로그인 POST IP당 5/minute·20/hour, scrypt, 계정 영구 잠금 없음 | 분산 IP 공격은 외부 WAF·공유 limiter 필요 |
| TM-02 | 존재하지 않는 사용자·dormant 계정 enumeration | 모두 401, 같은 일반 메시지·template 구조, 없는/dormant는 앱 시작 시 만든 dummy scrypt hash 검증 | DB 조회와 실제/dummy hash의 미세 timing 차이는 완전 제거되지 않음 |
| TM-03 | 로그인 전 session fixation | 성공 직전 `session.clear()`, fresh non-remember login, permanent 8시간 session | Secret Key·TLS 운영이 잘못되면 cookie 보호 약화 |
| TM-04 | dormant session의 stale resurrection | user loader가 inactive 시 인증 키를 제거하고 Phase 05 상태 service가 dormant/active마다 version 증가·Socket disconnect를 수행 | cross-process Socket invalidation은 운영 배포 통제 필요 |
| TM-05 | 비밀번호 변경 뒤 다른 browser session reuse | hash와 `auth_version` 동시 commit, loader exact version 비교, 현재 browser만 새 session 수립 | 이미 진행 중인 동시 요청 처리 경계는 배포 환경에서 추가 관찰 필요 |
| TM-06 | auth_version 누락·변조 cookie | 서명된 session + 버전 존재·정확 일치 요구, mismatch 인증 키 purge | Secret Key 노출 시 서명 보호 자체가 무력화됨 |
| TM-07 | CSRF logout·profile·password 변경 | 전역 Flask-WTF CSRF, 상태 변경 POST, SameSite=Lax | XSS가 생기면 동일 origin 요청은 가능하므로 XSS 완화 병행 |
| TM-08 | 저장 XSS bio | 최대 500자, Markup/`safe` 금지, Jinja autoescape, self-only CSP | 후속 richer text 기능 추가 시 재설계 필요 |
| TM-09 | 공개 profile 과다 노출 | active 사용자만, username·bio allowlist, UUID/hash/role/status/version/balance 제외 | username·bio 자체는 의도된 공개 정보 |
| TM-10 | 사용자 검색 자원 고갈·SQL injection | q 32, page 1~1000, fixed 20, ORM binding, 60/minute | 대규모 데이터에서는 index·query plan 검토 필요 |
| TM-11 | 가입 race와 부분 생성 | 사전 중복 조회, DB UNIQUE, IntegrityError rollback, User+Wallet 단일 commit | SQLite 쓰기 경쟁은 운영 부하와 함께 검토 필요 |
| TM-12 | 오류를 통한 내부 정보 노출 | 일반 400/401/404/429/500, 500 rollback, 공통 보안 header | server-side 로그 redaction 운영 절차 필요 |

## Phase 06 Wallet·Transfer 위협

아래 완화는 Phase 06 구현과 로컬 자동 검증 결과를 반영한다. 관련 Finding은 실제
file-based SQLite 독립 session 동시성 시험을 포함한 전체 596개 테스트 통과 뒤에만
`Mitigated`로 갱신했다.

| ID | 위협 | 구현된 완화 | 잔여 위험 |
|---|---|---|---|
| TM-51 | application에서 balance를 읽고 차감하는 race로 동시 송금이 모두 성공해 음수 잔액·이중 지출 발생 | `balance >= amount` 조건부 SQL debit, rowcount, Wallet nonnegative CHECK, Transfer·debit·credit·audit 단일 transaction과 독립 session concurrency 시험 | SQLite 이상의 높은 write concurrency·다중 process 환경은 운영 DB에서 별도 부하·격리 검증 필요 |
| TM-52 | browser 재시도·중복 클릭·network 재전송으로 같은 송금이 여러 번 반영 | GET마다 고엔트로 token, sender-bound SHA-256 key, DB UNIQUE, 같은 payload는 기존 결과, 동시 같은 token 시험 | token을 탈취한 동일 sender session 공격은 CSRF·현재 password·session 보호에 의존 |
| TM-53 | 같은 idempotency token을 다른 recipient 또는 amount에 재사용해 요청 의미를 바꿈 | 기존 Transfer의 sender/recipient/amount exact 비교, 불일치는 409 conflict, balance·row 불변 | 미래 payload field 추가 시 idempotency 비교 범위를 함께 갱신해야 함 |
| TM-54 | recipient 조회 뒤 status·Wallet이 바뀌는 TOCTOU로 dormant/missing 대상에 일부 반영 | service가 active User와 Wallet을 재조회하고 credit rowcount 실패를 전체 rollback하며 sender도 service에서 재검증 | SQLite transaction 격리보다 강한 동시 status 변경 요구는 운영 DB에서 재평가 필요 |
| TM-55 | client sender/recipient ID·balance·Transfer ID를 믿어 mass assignment 또는 타인 history/detail IDOR | sender=current user, recipient=username server lookup, ID/balance/key form 부재, participant history/detail query, 관리자 최소 projection·GET-only | participant가 합법적으로 본 counterpart·amount를 별도 유출하는 것은 application이 회수할 수 없음 |
| TM-56 | 열린 browser나 탈취한 current password로 공격자가 송금 | POST+CSRF, SameSite, current password 재확인, 사용자 3/minute·10/hour, generic 오류와 no-store | 현재 password와 authenticated session을 함께 탈취한 공격은 MFA·transaction confirmation 같은 범위 밖 통제가 필요 |
| TM-57 | SQLite write lock 경쟁으로 timeout·가용성 저하 또는 재시도 폭주 | 5000ms busy timeout, 짧은 원자 transaction, idempotent retry, bounded rate limit; WAL은 강제하지 않음 | SQLite는 고 write·다중 process 금융 원장용 DB가 아니며 본 과제는 실제 금융 서비스가 아님 |
| TM-58 | 과제용 포인트를 현금·결제 수단으로 오인하거나 실제 금융 기능으로 확장 | 모든 Wallet 화면·문서의 가상 포인트 고지, 외부 결제·충전·환전·출금·환불 route 부재 | 운영자가 범위를 변경하면 법적·회계·결제 보안 요구사항을 새로 설계해야 함 |
| TM-59 | DB commit을 실행한 뒤 예외가 발생해 결과가 불확실한데 새 token으로 재시도하여 같은 의도가 두 송금으로 반영 | `DATABASE_ERROR` form에 유효한 원 token을 hidden 유지하고 같은 payload의 기존 Transfer를 `IDEMPOTENT`로 조회하며 다른 payload는 conflict; 실제 commit 후 exception 재시도 시험 | 사용자가 원 token을 잃거나 다른 client에서 새 form으로 시작하면 application이 두 의도의 동일성을 자동 추론할 수 없음 |
| TM-60 | 같은 host의 다른 계정이 과도한 SQLite/instance mode를 이용해 password hash·채팅·신고·송금·감사 파일을 읽음 | POSIX instance `0700`, file SQLite main DB `0600`, descriptor type/inode 확인과 symlink/non-directory/non-regular fail closed; in-memory skip | non-POSIX ACL, host 관리자·소유자 계정 탈취와 별도 backup file 권한은 배포 통제 필요 |
| TM-61 | CI shallow checkout 또는 누락 tag 때문에 `git show` 기반 migration immutability 검증이 실행되지 못하거나 잘못 실패 | checkout `fetch-depth: 0`, credentials 미보존, Phase 01~05 tag를 checkout 직후 `git show-ref --verify`하고 필수 migration tests 실행 | tag 자체의 권한 있는 이동·삭제는 repository tag 보호와 사람 검토가 필요하며 Download ZIP에서는 해당 불변 테스트를 실행할 수 없음 |

## Phase 05 신고·관리자·감사 위협

| ID | 위협 | 구현된 완화 | 잔여 위험 |
|---|---|---|---|
| TM-38 | 자기·중복 신고와 client reporter/target/type 위조 | current user·URL server target, 존재/상태/소유권 검사, reporter-target UNIQUE 사전/race 처리 | 여러 정상 계정을 가진 공격자의 Sybil 신고는 완전히 식별하지 못함 |
| TM-39 | 다계정 허위 신고로 자동 제재 DoS | 사용자 shared 10/hour, 서로 다른 pending/confirmed 신고자 3명, rejected 제외, 관리자 검토·복구·audit | 계정 생성 비용이 낮으면 3개 계정 조율이 가능해 운영 신뢰/연령 신호가 추가로 필요 |
| TM-40 | admin 계정 3건 신고로 관리 기능 lockout | admin 대상 신고는 저장하되 자동 dormant 제외, 다른 admin 수동 검토, self/last-active-admin 보호 | 악성 admin과 credential 탈취는 MFA·조직 승인 같은 배포 통제가 필요 |
| TM-41 | 관리자 URL 직접 접근과 IDOR | 모든 route `admin_required`, active role DB 검사, URL target server query, 없는 UUID 404 | admin 계정 탈취 시 해당 권한 범위의 영향은 남음 |
| TM-42 | role/status/actor/target mass assignment | 일반 가입 role=user 고정, CLI-only admin, web role route 없음, mutation action allowlist와 current actor 사용 | 미래 JSON/bulk API는 동일 allowlist를 별도로 적용해야 함 |
| TM-43 | 관리자 mutation CSRF 또는 열린 browser 악용 | POST-only, Flask-WTF CSRF, SameSite, current password 재인증, shared 60/hour | 저장 XSS나 password manager 오용은 동일 origin 공격 영향 증가 가능 |
| TM-44 | last admin 또는 자기 dormancy에 의한 lockout | self dormancy 거부, 대상 admin 제외 active-admin count 검사, 상태와 audit 원자 commit | 동시 다중 worker/DB 격리 수준에서 serializable 보장이 필요한 대규모 배포는 별도 검토 |
| TM-45 | dormant/active 뒤 stale HTTP·Socket 부활 | 각 실제 전이 version 증가, 같은 transaction audit, commit 후 user Socket disconnect, loader/connect/event exact version | cross-process Socket invalidation은 process-local registry의 운영 잔여 위험 |
| TM-46 | 감사 누락으로 관리자 조치 부인 | mutation/auto restriction과 AuditLog 같은 transaction, audit 실패 전체 rollback, system actor 구분 | DB 권한을 가진 운영자는 직접 변조할 수 있어 외부 append-only 수집이 배포 범위 |
| TM-47 | 감사 details의 비밀번호·token·reason 2차 노출 | action별 scalar key allowlist, 민감 key 거부, request payload 전체 미저장, read-only admin UI | 잘못 allowlist된 일반 string 값의 의미적 비밀은 review가 계속 필요 |
| TM-48 | 관리자 신고 reason/message/title/username 저장 XSS | Jinja autoescape, JSON `safe`/Markup·inline script/style 금지, CSP, 악성 문자열 HTTP 테스트 | 미래 rich-text/내보내기 기능은 별도 context-aware encoding 필요 |
| TM-49 | 관리자 filter SQL injection·대량 조회 | WTForms choice/길이/page 1~1000, ORM binding·autoescape contains, fixed 50 SQL LIMIT | 복잡한 검색과 대규모 table은 query plan·index 운영 관찰 필요 |
| TM-50 | 메시지 hide를 이미 전달된 DOM 삭제로 오인 | hidden history 제외 정책과 UI 문서화, 복구 가능, audit | 이미 본 사용자·browser cache·screenshot에서 과거 내용 회수는 불가능 |

## Phase 04 실시간 채팅 위협

| ID | 위협 | 구현된 완화 | 잔여 위험 |
|---|---|---|---|
| TM-28 | 비인증 Socket 또는 Cross-Site WebSocket Hijacking | exact connect auth, Flask-WTF CSRF, active/version/current user 확인, Engine.IO same-origin, SameSite cookie | origin proxy 설정 오류와 Secret Key 유출은 별도 운영 통제 |
| TM-29 | client username/sender ID로 발신자 위조 | sender field 미수용, registry의 server-authenticated user ID와 DB username만 저장·emit | 계정 자체 탈취는 인증 통제 대상 |
| TM-30 | conversation UUID·arbitrary room으로 direct IDOR | route/event participant query, canonical UUID, server-only room, 타인/없는 동일 404·`not_found`, direct room emit | UUID 자체 노출은 권한 부여가 아니지만 로그 redaction 유지 필요 |
| TM-31 | 저장 message XSS | NFC/길이/control 검증, Jinja autoescape, browser createElement+textContent, self CSP, `safe`/Markup/inline script 금지 | 미래 rich text는 별도 sanitizer와 threat model 필요 |
| TM-32 | message/join spam과 여러 Socket quota 우회 | user ID 기준 global/direct 합산 5/10초·120/hour, join 30/60초, malformed send quota 소비, 5 connection cap | app memory limiter/cap은 worker 사이 공유되지 않음 |
| TM-33 | oversized/malformed Socket packet으로 자원 고갈·오류 정보 노출 | Engine.IO max 8192 bytes, exact event key/type, 500 char·2000 byte, control 거부, generic ack/error, args 미로그 | application 앞단의 connection/handshake rate 제한은 배포 계층 필요 |
| TM-34 | logout/password 변경 뒤 장시간 Socket 계속 송수신 | per-app registry version snapshot, 즉시 user disconnect, event/broadcast 전 missing/dormant/version/1800초 stale prune | 다중 worker에서는 cross-process invalidation 필요 |
| TM-35 | dormant 후 active 복구 시 과거 Socket 부활 | dormant 시 registry 제거와 server disconnect; restore는 새 authenticated connect만 허용 | 네트워크 단절 감지는 Engine.IO monitor와 배포 timeout에 의존 |
| TM-36 | DB 실패 message가 화면에만 전달되는 불일치 | sender/scope/body를 한 commit, 실패 rollback, commit 성공 후에만 stale prune·room emit | commit 뒤 process crash로 broadcast가 누락될 수 있으며 durable queue는 현재 범위 아님 |
| TM-37 | local browser dependency 공급망 변조 | 공식 Socket.IO 4.8.3 exact URL, SHA-384 검증, bundle license banner 유지, local self-host+SRI, runtime CDN 없음 | dependency 갱신 시 공식 byte·license·hash를 다시 검토해야 함 |

## Phase 03 상품·이미지·검색 위협

| ID | 위협 | 구현된 완화 | 잔여 위험 |
|---|---|---|---|
| TM-13 | Product UUID만 믿는 수정·삭제·상태 IDOR | current user owner query, 타인/없는 객체 동일 404, login/CSRF, Phase 05 관리자 active RBAC와 route-derived target | admin 계정 탈취 시 허용된 관리 범위의 영향은 남음 |
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
- chat registry, event limiter와 room membership도 process local이다. 다중 worker는 shared
  quota/presence store, Socket.IO message queue와 logout/version/dormant invalidation
  broadcast가 필요하다.
- HTTPS 종료, HSTS, Secret Key rotation, 백업·복구, 중앙 로그 redaction, 관리자 MFA는 배포
  범위에서 별도 검증해야 한다.
- 계정 복구, 이메일 검증, MFA는 현재 과제 범위에 없다.
- SQLite는 높은 쓰기 동시성에 한계가 있다. Phase 06은 file DB 독립 session concurrency와
  5000ms busy timeout을 검증 대상으로 포함하지만 다중 process·고부하 운영 보장은 하지 않는다.
- SQLite/instance mode 강제는 POSIX Ubuntu/WSL·GitHub Ubuntu 범위다. non-POSIX는 OS별 ACL을
  별도로 검증해야 하며 host 관리자와 별도 backup 권한까지 보호하지 않는다.
- CI는 전체 history와 Phase tag 존재를 검증하지만 권한 있는 tag 이동·삭제 자체를 막지
  않으므로 repository tag 보호와 review가 필요하다.
- Wallet·Transfer는 실제 금융 자산이 아니며 영구 cloud 배포, 실제 은행·카드·결제·충전·
  환전·출금·환불 연동은 범위 밖이다.
