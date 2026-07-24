# Security Findings

## 기준선과 상태 기준

- 기준 커밋: `f0dd4baac057f62315bb4850f05d18b7e60eb4be`
- SEC-01~17 근거는 해당 커밋의 `app.py`, `templates/`, `enviroments.yaml`을 직접 정적
  분석한 실제 줄 번호다. SEC-18은 `phase-01-foundation` user loader, SEC-19·20은
  Phase 03 설계·위협 모델·구현 검토에서 발견했다. SEC-21·22는 Phase 04, SEC-23~25는
  Phase 05, SEC-26~28은 Phase 06 송금 설계·구현 검토에서 발견했다. SEC-29·30은 Phase 06
  최종 사람 코드 검토에서 발견했다.
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
| SEC-04 | `templates/register.html:5`, `templates/profile.html:6`, `app.py:108` | High | 가입·프로필·상품·채팅·신고·관리자·송금을 사용자 의사 없이 유도 가능 | 모든 HTTP mutation에 POST+Flask-WTF CSRF를 적용하고 관리자와 송금은 current password를 재확인한다. | Mitigated | Testing CSRF 활성, 송금 token 누락 400, Socket CSRF와 mutation GET 405 자동 테스트 |
| SEC-05 | `app.py:203` | High | 비인증·cross-site Socket.IO client가 채팅 전송 가능 | connect CSRF, same-origin, active 인증과 DB version 확인, event마다 registry/current user/DB 재검증, stale disconnect | Mitigated | 비인증·missing/invalid/다른 session CSRF·dormant/version connect와 stale event 자동 테스트 |
| SEC-06 | `templates/dashboard.html:39`, `app.py:204` | High | client 제공 username으로 다른 발신자를 가장해 메시지 전송 가능 | client sender field 미수용, current server-authenticated user ID와 DB username만 sender로 저장·emit | Mitigated | global/direct username·sender_id extra key 거부와 저장 sender 자동 테스트 |
| SEC-07 | `app.py:204` | Medium | 메시지 형식·길이 제한 부재로 저장 XSS, spam, 자원 고갈 위험 | strict event schema, NFC/newline/1~500자·2000 bytes/control 검증, Jinja escape·textContent, user event limit, 8192-byte packet | Mitigated | 입력 경계·정규화·control·XSS·burst/hour/multi-socket/static DOM 자동 테스트 |
| SEC-08 | `app.py:70`, `app.py:136`, `app.py:187` | High | 가입·프로필·상품·채팅·신고·관리자·송금 입력의 무제한 값으로 데이터 오염, XSS와 자원 남용 가능 | 송금 recipient username, bool 제외 amount 1~1B, current password 길이와 43자 URL-safe token을 form/service에서 재검증하고 history query를 allowlist한다. | Mitigated | username·amount·token 경계, password 미반사, query SQLi 형태와 extra field 자동 테스트 |
| SEC-09 | `app.py:49`, `app.py:188` | High | 신고 대상 type·존재·중복·자기 대상 미검사로 허위 신고와 자동 제재 조작 가능 | server-derived reporter/type/target, 상태·소유권, UNIQUE race, distinct 3명 count, admin 예외·검토·복구를 원자 구현했다. | Mitigated | 사용자·상품 정상/자기/없는/상태/중복/race/rejected/threshold/admin 예외·rollback 테스트 |
| SEC-10 | `app.py:31-57` | High | FK/CHECK/NOT NULL/업무 UNIQUE 부재로 고아·음수·범위 밖·중복 원장과 잘못된 상태 저장 가능 | 기존 DB 제약에 Transfer amount 1~1B와 64 lowercase hex key named CHECK, sender/recipient history index를 여섯 번째 migration으로 추가하고 unique/FK/distinct-user를 유지한다. | Mitigated | amount/key DB 경계, index/constraint introspection, upgrade/downgrade/re-upgrade와 두 drift check |
| SEC-11 | `app.py:6`, `app.py:98` | Medium | 세션 쿠키 보호·만료 정책 부재로 탈취·고정·장기 재사용 위험 | HttpOnly, SameSite=Lax, 8시간 permanent session, 운영 Secure, strong protection, 로그인 `session.clear()`, fresh non-remember login과 password 변경 `auth_version` 회전을 구현했다. 실제 TLS 종료는 배포 범위다. | Partial | cookie/config, fixation marker 제거, remember 부재, 버전 mismatch·다중 client 자동 테스트; 실제 HTTPS/WSS 수동 검증 예정 |
| SEC-12 | `app.py:89`, `app.py:182` | Medium | 로그인·상품·채팅·신고·송금 요청 반복으로 brute force·spam·write lock 가용성 저하 가능 | Wallet GET IP 60/minute와 송금 사용자 shared 3/minute·10/hour를 기존 HTTP/Socket/신고/admin limit에 추가했다. 단일-process memory backend는 다중 process 전체 quota를 공유하지 않는다. | Partial | 송금 minute/hour와 기존 limit 자동 테스트 통과; 운영 shared limiter 저장소 통합은 잔여 위험 |
| SEC-13 | `app.py:70`, `app.py:204` | Medium | 처리되지 않은 입력·이벤트 오류가 stack·경로·내부 상태를 노출할 수 있음 | 공통 HTTP handler와 Socket namespace generic error handler, service rollback·commit 전 미broadcast, event name-only redacted log | Mitigated | HTTP 오류와 Socket 강제 exception의 client payload·server log 자동 테스트 |
| SEC-14 | `templates/base.html:3`, `app.py:6` | Medium | 보안 응답 header 부재로 clickjacking, MIME sniffing과 XSS 영향 증가 | 중앙 after-request에서 CSP, nosniff, DENY, referrer와 permissions 정책 적용 | Mitigated | 정상·오류 응답 header 테스트 |
| SEC-15 | `enviroments.yaml:5-10`, `templates/base.html:7` | Medium | 버전 미고정 의존성과 외부 CDN 공급망으로 재현성 저하·악성 자산 노출 가능 | runtime/dev exact pin, Socket.IO 4.8.3 공식 byte SHA-384 검증·MIT notice·local SRI, runtime CDN 없음 | Mitigated | requirements audit, bundle hash/banner, template local URL/integrity 정적 테스트 |
| SEC-16 | `app.py:208-210` | Medium | 직접 실행에서만 스키마를 생성해 WSGI 기동 시 누락과 schema drift 발생 가능 | 최초 Alembic migration과 명시적 upgrade 절차로 교체 | Mitigated | 임시 빈 DB migration upgrade와 `flask db check` |
| SEC-17 | `app.py:122`, `app.py:142`, `app.py:178` | Medium | `SELECT *`로 비밀번호·소유권·파일명 등 불필요 필드를 조회·전달해 노출 범위 증가 | 공개 사용자와 공개 상품 모두 명시 SELECT projection과 frozen·slots DTO만 template에 전달한다. 상품은 seller_id/image_filename과 User id/hash/role/status/version/Wallet을 projection에서 제외한다. | Mitigated | 실제 사용자·상품 SQL SELECT 절, DTO field allowlist, route context와 응답 금지 필드 자동 테스트 |
| SEC-18 | `phase-01-foundation:app/__init__.py` user loader | Medium | dormant User는 `None`이었지만 인증 session key가 남아 관리자가 다시 active로 바꾸면 과거 session cookie가 다시 인증될 수 있었다. 비밀번호 변경 뒤 다른 session을 구분할 버전도 없었다. | `User.auth_version`, 로그인 session 버전 저장, loader의 active·exact version 확인과 인증 키 purge를 구현했다. dormant로 anonymous가 된 뒤 active로 복구해도 과거 session은 계속 anonymous이며 password 변경은 다른 client를 무효화한다. | Mitigated | dormant 기존 session 차단, 재활성화 후 부활 방지, version 누락·mismatch, password 변경 후 다른 client 차단 자동 테스트 |
| SEC-19 | Phase 03 설계·구현 검토 | High | 상품 IDOR와 mass assignment로 타인 상품 수정·삭제, 소유자·제재 상태 변경 가능 | current user owner query, 타인/없는 동일 404, form/service field allowlist, active↔sold만 허용, CSRF와 rate limit | Mitigated | 타인 edit/status/delete, 임의 seller/status/image field, hidden/deleted 복구 자동 테스트 |
| SEC-20 | Phase 03 위협 모델·구현 및 사람 최종 검토 | High | 확장자 신뢰, traversal, configured root/file symlink, filesystem TOCTOU·저장 후 변조, polyglot, metadata, animation·decompression bomb, direct URL로 코드·정보 노출 또는 DoS 가능 | bounded decode/verify, upload/read format·dimension·pixel 재검사, 재인코딩·metadata 제거, random filename, root lstat/open/fstat identity, root dir_fd 상대 create/read/remove, 0700/0600, file/DB cleanup, 비공개 image 정책 | Mitigated | 위장·손상·path·bomb·animation·metadata·polyglot, configured root/file symlink·dir_fd·inode mismatch, read-time dimension/pixel, rollback·상태별 image 자동 테스트 |
| SEC-21 | Phase 04·05 설계 검토 | High | HTTP logout·password 변경·moderation dormant/active 이후 장시간 Socket이나 cookie가 다시 유효해질 수 있음 | Phase 05 실제 status service가 매 전이 version을 증가시키고 audit와 commit한 뒤 user Socket을 즉시 disconnect한다. loader/connect/event exact version을 유지한다. | Mitigated | auto/admin dormant disconnect, old cookie 무효, active 복구 version 증가·새 login만 허용 테스트 |
| SEC-22 | Phase 04 설계·구현 검토 | High | conversation ID나 room name을 신뢰하면 타인의 1대1 대화·message 접근 가능 | canonical conversation, route/event participant query, server-only room, arbitrary room 미수용, 타인/없는 동일 응답, direct room-only emit | Mitigated | participant/제3자 route·join·send·수신·room scope 자동 테스트 |
| SEC-23 | Phase 05 설계·구현 검토 | High | 중복·자기 신고 또는 다계정 신고로 자동 제재를 조작해 가용성을 훼손 가능 | server-derived reporter/target, 상태·소유권, UNIQUE, shared rate limit, distinct threshold, admin 자동 dormant 제외, review/recovery/audit와 원자 race 처리 | Mitigated | 신고 경계·중복·race·1/2/3명·rejected·admin 예외·rollback 테스트 |
| SEC-24 | Phase 05 설계·구현 검토 | High | 관리자 URL 직접 접근, mass assignment, CSRF·재인증 부재로 권한 상승 또는 임의 상태 변경 가능 | active `admin_required`, 가입 role=user, CLI-only admin, POST+CSRF+current password, URL target, action allowlist, self/last-admin 보호 | Mitigated | anonymous/user/dormant/admin RBAC, CSRF/reauth, role/target spoof, GET 405와 상태 전이 테스트 |
| SEC-25 | Phase 05·06 설계·구현 검토 | High | 감사 누락 또는 민감정보 기록으로 부인 방지 실패와 비밀정보 2차 노출 가능 | `transfer.created`와 Transfer·debit·credit를 같은 transaction에 두고 details는 amount만 허용하며 recipient·balance·password·raw/derived token을 제외한다. 외부 append-only/WORM 감사 저장소는 없다. | Partial | transfer audit 실패 rollback과 amount-only redaction 자동 테스트 통과; 외부 감사 저장소는 운영 잔여 위험 |
| SEC-26 | Phase 06 송금 설계·구현 검토 | High | balance를 application에서 읽고 차감하면 동시 송금으로 이중 지출·음수 잔액·원장 불일치 가능 | DB 조건부 debit, `balance >= amount`, rowcount, Wallet CHECK와 Transfer·debit·credit·audit 단일 transaction을 구현했다. | Mitigated | 실제 file SQLite 독립 session의 80+80 경쟁, 성공 원장/debit 일치와 총 잔액 불변 자동 테스트 |
| SEC-27 | Phase 06 송금 설계·구현 검토 | High | browser 재시도·중복 클릭·network 재전송으로 같은 송금이 여러 번 반영될 수 있음 | 서버 생성 고엔트로 token, sender-bound SHA-256 key, DB UNIQUE, 같은 payload 기존 결과와 다른 payload conflict를 구현하고 raw token/key를 UI·audit에서 제외했다. | Mitigated | 순차·동시 같은 token, 다른 amount/recipient, sender namespace와 redaction 자동 테스트 |
| SEC-28 | Phase 06 송금 설계·구현 검토 | High | sender/recipient ID·balance·Transfer ID를 신뢰하면 mass assignment와 타인 송금 이력 IDOR 가능 | sender=current user, recipient=username server lookup, ID/balance/key form 부재, current-user history filter, detail participant query와 관리자 read-only projection을 구현했다. | Mitigated | extra field, 제3자/missing 동일 404, projection SELECT와 admin GET-only 자동 테스트 |
| SEC-29 | Phase 06 최종 사람 코드 검토 | Medium | DB commit 결과가 불확실한 오류 뒤 idempotency token을 교체하면 사용자의 재시도가 새 송금으로 처리될 수 있음 | `DATABASE_ERROR`에서는 유효한 원 token을 hidden input에 유지하고 같은 token 재시도의 기존 Transfer를 조회한다. 같은 payload는 `IDEMPOTENT`, 다른 payload는 conflict이며 token은 hidden 외 미노출이다. | Mitigated | 실제 commit 후 exception과 같은 token HTTP 재시도에서 Transfer·audit·debit·credit 1회 및 visible text·flash·로그 redaction 자동 테스트 |
| SEC-30 | Phase 06 최종 사람 코드 검토 | Medium | SQLite DB와 instance directory 권한을 OS 기본값에 맡기면 동일 시스템의 다른 계정이 password hash, 채팅, 신고, 송금·감사 데이터를 읽을 위험 | POSIX에서 instance `0700`, file-backed SQLite main DB `0600`, symlink/non-directory/non-regular fail closed와 descriptor 기반 권한 적용을 구현했다. | Mitigated | 실제 instance/DB mode, in-memory skip, symlink 거부, FK·busy timeout 유지와 전체 자동 테스트 |

## SEC-19 상세

- 주제: 상품 객체 단위 권한 검사를 빠뜨릴 경우의 IDOR와 mass assignment 위험
- 발견 단계: Phase 03 설계·구현 검토
- 심각도: High
- 위험: URL의 Product ID만 신뢰하면 타인 상품 수정·삭제·상태 변경이 가능하고, form의
  seller_id/status/image_filename을 사용하면 소유권과 hidden/deleted 제재를 우회할 수 있다.
- 완화: 모든 owner mutation query에 `current_user.id`를 넣고 타인과 없는 row를 동일 404로
  처리한다. create/edit form과 service 인자에서 소유권·상태·파일명 필드를 제거하고 임의
  POST field를 무시한다. 생성은 active, 소유자 전이는 active↔sold만 허용하며
  hidden/deleted 복구를 금지한다. CSRF와 사용자 rate limit을 함께 적용했다.
- 검증: 타인 수정·상태·삭제, 임의 필드, hidden/deleted 수정·복구, soft delete의 DB·HTTP
  상태 자동 테스트가 통과한 뒤 Mitigated로 기록했다.

## SEC-20 상세

- 주제: 이미지 업로드의 확장자 신뢰, 경로 순회, configured root/file symlink,
  filesystem TOCTOU·저장 후 변조, polyglot, metadata, decompression bomb 위험
- 발견 단계: Phase 03 위협 모델·구현과 사람 최종 코드 검토
- 심각도: High
- 위험: client filename·Content-Type·확장자를 믿으면 script/SVG나 decoder 공격 파일,
  traversal 경로, metadata 개인정보와 trailing executable payload를 저장할 수 있다. upload
  root 자체가 symlink면 외부 target에 생성·읽기·삭제·chmod가 발생할 수 있고 path 검사와
  open 사이 교체 또는 저장 후 local 변조도 검증을 우회할 수 있다. pixel bomb·animation은
  CPU/memory 고갈, direct URL은 hidden/deleted 정보 노출을 유발한다.
- 완화: 요청 5 MiB, 파일 입력·출력 4 MiB, 각 변 4096px, 16M pixel을 제한한다. Pillow 실제
  decode·verify와 warning-as-error, format/extension·single-frame 검사를 수행한 뒤 EXIF
  transpose, RGB/RGBA 변환, metadata 없는 서버 재인코딩을 한다. 32 hex random filename,
  web root 밖 저장을 적용한다. configured root는 resolve하지 않고 final component
  lstat→직접 open→fstat의 directory·device/inode identity를 검사한다. create/read/remove는
  모두 열린 root dir_fd에 대한 상대 filename만 사용하며 file stat/open/fstat identity,
  가능한 O_NOFOLLOW/O_CLOEXEC, descriptor fchmod 0700/0600을 적용한다. 읽을 때도 실제
  format/extension, positive dimension, 현재 dimension/pixel limit, single frame,
  warning-as-error와 verify를 다시 수행한다. DB 실패 cleanup과 상품 공개 상태 검사도
  적용했다.
- 검증: 비이미지/SVG/GIF/손상/mismatch/path/empty/oversize/dimension/pixel/animation,
  EXIF·metadata·trailing marker, filename 충돌, unsafe DB filename·symlink·missing,
  configured root symlink에서 store/read/remove 거부와 target file/mode 불변, dir_fd 상대
  저장, root inode mismatch descriptor cleanup, read-time JPEG/PNG/WebP dimension·pixel,
  MIME/header/cache, hidden/deleted owner/other 접근과 DB failure cleanup 자동 테스트 및
  전체 검증 명령이 통과한 뒤 Mitigated 상태를 유지한다.

## SEC-21 상세

- 주제: HTTP logout·password 변경·dormant 이후 장시간 Socket connection이 계속
  송수신할 위험
- 발견 단계: Phase 04 설계 검토
- 심각도: High
- 위험: Socket 연결 시점에만 인증하면 HTTP session 종료, password 변경에 따른
  `auth_version` 회전이나 사용자 dormant 이후에도 이미 연결된 sid가 room message를 보내고
  받을 수 있다. dormant 후 active 복구 때 과거 연결이 다시 유효해지는 stale resurrection도
  가능하다.
- 완화: app별 RLock registry가 sid별 user ID, auth version과 monotonic 연결 시각을
  보관한다. 모든 inbound event와 room broadcast 전에 snapshot user를 batch 조회해
  missing/dormant/version mismatch/1800초 초과 sid를 제거한다. logout은 user ID를 보존해
  `logout_user()` 전에, password 변경은 hash/version commit 뒤 새 HTTP session 수립 전에
  해당 user socket을 모두 disconnect한다. user당 connection은 5개로 제한한다.
- 검증: logout 직후 disconnect·이후 미수신, password 변경 직후 old disconnect·새 session
  connect, old version send 거부, dormant broadcast 전 제거·미수신, active 복구 뒤 미부활,
  max-age event·다른 사용자 broadcast 전 제거 자동 테스트가 통과한 뒤 Mitigated로
  기록했다.

## SEC-22 상세

- 주제: 1대1 conversation ID 또는 room name을 신뢰할 경우 타인의 대화·메시지에 접근하는
  IDOR
- 발견 단계: Phase 04 설계·구현 검토
- 심각도: High
- 위험: UUID가 추측하기 어렵더라도 노출·공유된 conversation ID만으로 page·history·join·send를
  허용하거나 client room 문자열을 그대로 join하면 제3자가 두 참여자의 message를 읽거나
  주입할 수 있다.
- 완화: direct pair는 UUID sorted canonical CHECK·UNIQUE를 유지한다. route, join과 send마다
  현재 authenticated user가 user1/user2인지 query한다. client room name은 받지 않고
  canonical conversation ID로 server-only direct room을 만든다. 타인과 없는 conversation은
  같은 HTTP 404 또는 Socket `not_found`이며 message는 해당 direct room에만 emit한다.
- 검증: 두 participant page/join/send 성공, nonparticipant와 missing 동일 오류, arbitrary
  room·invalid UUID·다른 conversation send 거부, 두 participant만 수신하고 제3자/global
  room은 미수신하는 자동 테스트가 통과한 뒤 Mitigated로 기록했다.

## SEC-23 상세

- 주제: 중복·자기 신고와 다계정 신고를 이용한 자동 제재 남용
- 심각도: High
- 완화: reporter와 URL target/type을 서버가 결정하고 대상 존재·상태·소유권, 신고자-대상
  UNIQUE 사전/race, 사용자·상품 shared 10/hour와 `pending`/`confirmed`의 서로 다른 신고자
  3명을 검사한다. admin 계정은 자동 dormant하지 않고 수동 review·recovery·audit를
  요구한다.
- 검증: 정상/자기/없는/비공개/중복/spoof/UNIQUE race/rejected 제외/세 번째 자동 제재,
  admin 예외와 audit failure 전체 rollback 자동 테스트가 통과한 뒤 Mitigated로 기록했다.
- 잔여 위험: Sybil 계정 자체를 식별하지 못하므로 운영 단계에서 계정 신뢰·연령·행동 신호와
  수동 검토가 필요하다.

## SEC-24 상세

- 주제: 관리자 URL 직접 접근, mass assignment, CSRF 또는 재인증 부재에 의한 권한 상승
- 심각도: High
- 완화: active `admin_required`를 모든 admin route에 적용하고 일반 가입 role=user,
  hidden-prompt CLI-only admin, POST+CSRF+current password, URL-derived target와 action
  allowlist를 사용한다. web role 변경, 자기 dormancy와 마지막 active admin 제거를
  허용하지 않는다.
- 검증: anonymous/일반/dormant/active RBAC, 모든 목록, CSRF 누락, 잘못된 password,
  role/seller/status/actor/target spoof, 잘못된 action/filter/page와 mutation GET 405 자동
  테스트가 통과한 뒤 Mitigated로 기록했다.

## SEC-25 상세

- 주제: 감사 로그 누락 또는 민감정보 기록으로 인한 부인 방지 실패와 비밀정보 2차 노출
- 심각도: High
- 완화: 관리/자동 제재와 AuditLog를 같은 transaction에 두고 실패 시 전체 rollback한다.
  Phase 06 `transfer.created`도 Transfer·debit·credit와 같은 transaction에서 만들고 details는
  amount만 허용한다.
  actor/action/target와 action별 scalar details만 허용하며 password/hash/Secret/CSRF/
  session/cookie/auth version/idempotency key/Socket sid/reason/token/balance/recipient를
  거부한다. UI는 system actor를 구분하고 projection·autoescape·read-only로 제공한다.
- 검증: audit 생성/commit 실패 rollback, actor와 details allowlist, XSS escape, reason
  미복제, 감사 수정·삭제 route 부재와 transfer audit 실패 전체 rollback·amount-only
  redaction 자동 테스트가 통과했다.
- 잔여 위험: 현재 AuditLog는 application DB 안에 있어 별도 append-only/WORM 저장소와
  외부 보존·경보 체계는 운영 단계에서 필요하다.

## SEC-26 상세

- 주제: balance를 application에서 읽고 차감할 경우 동시 송금에 의한 이중 지출과 음수 잔액
- 심각도: High
- 위험: 두 session이 같은 기존 balance를 읽고 각각 Python에서 차감해 commit하면 잔액보다
  많은 Transfer가 성공하거나 debit·credit·원장이 서로 어긋날 수 있다.
- 완화: `UPDATE wallets SET balance = balance - amount WHERE user_id = sender_id AND
  balance >= amount` 조건부 debit과 rowcount 1을 요구한다. Wallet nonnegative CHECK를
  유지하고 Transfer 예약, debit, credit와 amount-only audit를 단일 transaction에서 한 번만
  commit한다. 어느 단계든 실패하면 전체 rollback한다.
- 검증: 실제 file-based SQLite와 독립 session/thread에서 balance 100의 80+80 경쟁, 음수
  잔액 부재, 성공 Transfer 수와 debit 횟수 일치, 모든 Wallet 총합 불변과
  credit/audit/commit 실패 rollback 자동 테스트가 통과했다.

## SEC-27 상세

- 주제: browser 재시도·중복 클릭·network 재전송에 의한 중복 송금
- 심각도: High
- 위험: 같은 의도의 POST가 두 번 처리되면 사용자가 승인한 금액보다 여러 번 차감되고
  recipient도 여러 번 증가할 수 있다.
- 완화: GET마다 `secrets.token_urlsafe(32)` token을 만들고
  `sha256(sender_user_id + ":" + raw_token)` derived key를 DB UNIQUE로 예약한다. 같은
  sender/recipient/amount는 기존 결과를 반환하고 다른 recipient/amount는 conflict로
  거부한다. raw token은 DB·audit·로그·표시에서 제외하고 derived key도 UI·DTO·audit에서
  제외한다.
- 검증: 순차·동시 같은 token/payload의 원장·debit·credit 한 번, 다른 amount/recipient의
  conflict와 상태 불변, 다른 sender namespace, token/key redaction 자동 테스트가 통과했다.

## SEC-28 상세

- 주제: sender·recipient ID 또는 Transfer ID를 신뢰할 경우의 mass assignment와 송금 내역
  IDOR
- 심각도: High
- 위험: client ID·balance·DB key를 사용하면 타인 Wallet에서 차감하거나 임의 Wallet에
  credit할 수 있고, UUID만으로 detail/history를 허용하면 제3자가 송금 관계와 금액을 볼 수
  있다.
- 완화: sender는 current authenticated user로 고정하고 recipient는 username으로 active
  User와 Wallet을 서버 조회한다. form/service에 sender/recipient ID, balance와 DB key가
  없다. history는 current user sender/recipient 조건, detail은 participant query를 사용하고
  제3자와 missing을 같은 404로 처리한다. 관리자 Transfer는 최소 projection의 GET-only다.
- 검증: extra field 무시, 타인 history 배제, sender/recipient detail 허용, 제3자/missing
  동일 404, idempotency/internal user ID SELECT·DTO·HTML 제외와 admin mutation 부재 자동
  테스트가 통과했다.

## SEC-29 상세

- 발견 단계: Phase 06 최종 사람 코드 검토
- 심각도: Medium
- 주제: DB commit 결과가 불확실한 오류 뒤 idempotency token 교체에 의한 중복 송금 위험
- 위험: DB commit을 실제 실행한 뒤 연결·driver 예외가 발생하면 application은 성공 여부를
  단정할 수 없다. 이때 오류 form을 새 token으로 바꾸면 사용자의 재시도가 새 송금 의도로
  처리되어 이미 반영된 debit·credit·원장·감사를 반복할 수 있다.
- 완화: `DATABASE_ERROR`에서 제출된 유효 token을 hidden input 한 곳에 유지한다. 같은
  sender/token으로 재시도하면 기존 Transfer를 조회해 같은 recipient/amount는
  `IDEMPOTENT`로 같은 detail에 303 redirect하고, 다른 payload는 conflict로 거부한다.
  current password는 항상 form data에서 제거하며 token은 visible text·flash·로그·감사에
  노출하지 않는다. form validation과 확정된 업무 오류는 기존대로 새 token을 발급한다.
- 검증: commit wrapper가 원래 commit을 실행한 뒤 `SQLAlchemyError`를 발생시키는 실제 DB
  회귀에서 첫 응답은 일반 500과 동일 hidden token, 재시도는 같은 Transfer detail 303이며
  Transfer·AuditLog·debit·credit가 각각 한 번이고 balance가 400/100임을 확인했다. 전체
  596개 자동 테스트가 통과한 뒤 `Mitigated`로 기록했다.

## SEC-30 상세

- 발견 단계: Phase 06 최종 사람 코드 검토
- 심각도: Medium
- 주제: SQLite DB와 Flask instance directory의 과도한 filesystem 권한에 의한 local file
  disclosure
- 위험: OS 기본 umask와 생성 mode에만 의존하면 같은 host의 다른 계정이 scrypt password
  hash, 채팅, 신고, Transfer와 감사 데이터를 읽을 수 있다. instance/DB path가 symlink면
  의도하지 않은 target에 chmod하거나 DB를 열 위험도 있다.
- 완화: Flask instance final path를 생성 전 `lstat`하고 기존 symlink·non-directory를
  거부한다. POSIX에서는 directory descriptor의 type·inode identity를 확인하고 `fchmod`
  `0700`을 적용한다. SQLite connect의 기존 FK·busy timeout 설정 뒤 `PRAGMA database_list`로
  main file을 찾고 symlink·non-regular file을 거부하며 가능한 `O_NOFOLLOW`·`O_CLOEXEC`
  descriptor를 열어 `fchmod` `0600`을 적용한다. 모든 descriptor는 성공·실패 경로에서
  닫고 chmod 실패를 전파하며 process-wide umask는 바꾸지 않는다. in-memory SQLite는
  건너뛴다.
- 검증: Ubuntu/WSL POSIX 환경의 실제 instance `0700`, file SQLite `0600`, in-memory 정상
  동작, symlink/non-directory 거부, `foreign_keys=ON`과 `busy_timeout=5000` 유지 및 전체
  596개 자동 테스트가 통과한 뒤 `Mitigated`로 기록했다.
- 잔여 위험: non-POSIX에서는 POSIX mode 보장을 주장하지 않으며 OS별 ACL을 별도로 구성해야
  한다. host 관리자·DB 파일 소유자 권한 탈취, 허용된 process 메모리 읽기와 백업 파일 권한은
  이 완화 범위 밖이다.

## 종결 및 추적 원칙

현재 `Partial`인 SEC-11·12·25는 실제 HTTPS/WSS 배포, 다중-process 공유 limiter,
외부 append-only 감사 저장소라는 의도된 운영 잔여 위험이다. 최종 보고서는 Git 이력에서
실제 관련 commit을 조회해 SEC-18~30을 포함한 Finding별 관련 commit hash를 연결하며,
검증 실패나 미구현 범위를 `Mitigated`로 변경하지 않는다. 관련 commit은 최종 보고서
단계에서 Git 이력으로 연결한다.
