# Security Findings

## 기준선과 상태 기준

- 기준 커밋: `f0dd4baac057f62315bb4850f05d18b7e60eb4be`
- SEC-01~17 근거는 해당 커밋의 `app.py`, `templates/`, `enviroments.yaml`을 직접 정적
  분석한 실제 줄 번호다. SEC-18은 `phase-01-foundation` user loader, SEC-19·20은
  Phase 03 설계·위협 모델·구현 검토에서 발견했다. SEC-21·22는 Phase 04 설계·구현
  검토에서 발견했다.
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
| SEC-04 | `templates/register.html:5`, `templates/profile.html:6`, `app.py:108` | High | 가입·프로필·상품·채팅 변경을 사용자 의사 없이 유도 가능 | HTTP mutation 전역 CSRF와 Socket connect 전용 Flask-WTF CSRF를 적용하고 상태/삭제/message GET route를 두지 않는다. 신고·송금은 후속 Phase 검증이 남았다. | Partial | Testing CSRF 활성, HTTP token 누락 400, Socket missing/invalid/foreign token과 GET 405 테스트 |
| SEC-05 | `app.py:203` | High | 비인증·cross-site Socket.IO client가 채팅 전송 가능 | connect CSRF, same-origin, active 인증과 DB version 확인, event마다 registry/current user/DB 재검증, stale disconnect | Mitigated | 비인증·missing/invalid/다른 session CSRF·dormant/version connect와 stale event 자동 테스트 |
| SEC-06 | `templates/dashboard.html:39`, `app.py:204` | High | client 제공 username으로 다른 발신자를 가장해 메시지 전송 가능 | client sender field 미수용, current server-authenticated user ID와 DB username만 sender로 저장·emit | Mitigated | global/direct username·sender_id extra key 거부와 저장 sender 자동 테스트 |
| SEC-07 | `app.py:204` | Medium | 메시지 형식·길이 제한 부재로 저장 XSS, spam, 자원 고갈 위험 | strict event schema, NFC/newline/1~500자·2000 bytes/control 검증, Jinja escape·textContent, user event limit, 8192-byte packet | Mitigated | 입력 경계·정규화·control·XSS·burst/hour/multi-socket/static DOM 자동 테스트 |
| SEC-08 | `app.py:70`, `app.py:136`, `app.py:187` | High | 가입·프로필·상품·채팅·신고 입력의 무제한 값으로 데이터 오염, XSS와 자원 남용 가능 | 인증·사용자·상품과 채팅 message/event 입력을 form/service/DB에서 제한하고 저장 XSS를 시험했다. 신고 입력은 아직 미구현이다. | Partial | 인증·사용자·상품·chat HTTP/event 경계, DB range, XSS와 upload 검증 테스트 |
| SEC-09 | `app.py:49`, `app.py:188` | High | 신고 대상 type·존재·중복·자기 대상 미검사로 허위 신고와 자동 제재 조작 가능 | reporter/type/target UNIQUE와 target type CHECK는 구현, 대상·소유권·3명 집계 service는 후속 구현 필요 | Partial | DB 중복 테스트와 후속 존재/자기 대상/race/집계 테스트 |
| SEC-10 | `app.py:31-57` | High | FK/CHECK/NOT NULL/업무 UNIQUE 부재로 고아·음수·중복·잘못된 상태 저장 가능 | SQLAlchemy 모델, SQLite FK, CHECK/UNIQUE/NOT NULL에 더해 Phase 03 bounded price CHECK, image filename UNIQUE와 named query index를 세 번째 migration에 적용 | Mitigated | 가격 경계·filename 중복 IntegrityError, index introspection, migration upgrade/downgrade/check |
| SEC-11 | `app.py:6`, `app.py:98` | Medium | 세션 쿠키 보호·만료 정책 부재로 탈취·고정·장기 재사용 위험 | HttpOnly, SameSite=Lax, 8시간 permanent session, 운영 Secure, strong protection, 로그인 `session.clear()`, fresh non-remember login과 password 변경 `auth_version` 회전을 구현했다. | Mitigated | cookie/config, fixation marker 제거, remember 부재, 버전 mismatch·다중 client 테스트 |
| SEC-12 | `app.py:89`, `app.py:182` | Medium | 로그인·상품·채팅·신고 요청 반복으로 brute force·spam·가용성 저하 가능 | HTTP endpoint limit, chat 사용자 합산 5/10초·120/hour, join 30/60초와 connection cap을 적용했다. 신고 limit은 Phase 05에 남아 있다. | Partial | HTTP 429, Socket burst/hour/join·malformed·multi-socket·cap 자동 테스트 |
| SEC-13 | `app.py:70`, `app.py:204` | Medium | 처리되지 않은 입력·이벤트 오류가 stack·경로·내부 상태를 노출할 수 있음 | 공통 HTTP handler와 Socket namespace generic error handler, service rollback·commit 전 미broadcast, event name-only redacted log | Mitigated | HTTP 오류와 Socket 강제 exception의 client payload·server log 자동 테스트 |
| SEC-14 | `templates/base.html:3`, `app.py:6` | Medium | 보안 응답 header 부재로 clickjacking, MIME sniffing과 XSS 영향 증가 | 중앙 after-request에서 CSP, nosniff, DENY, referrer와 permissions 정책 적용 | Mitigated | 정상·오류 응답 header 테스트 |
| SEC-15 | `enviroments.yaml:5-10`, `templates/base.html:7` | Medium | 버전 미고정 의존성과 외부 CDN 공급망으로 재현성 저하·악성 자산 노출 가능 | runtime/dev exact pin, Socket.IO 4.8.3 공식 byte SHA-384 검증·MIT notice·local SRI, runtime CDN 없음 | Mitigated | requirements audit, bundle hash/banner, template local URL/integrity 정적 테스트 |
| SEC-16 | `app.py:208-210` | Medium | 직접 실행에서만 스키마를 생성해 WSGI 기동 시 누락과 schema drift 발생 가능 | 최초 Alembic migration과 명시적 upgrade 절차로 교체 | Mitigated | 임시 빈 DB migration upgrade와 `flask db check` |
| SEC-17 | `app.py:122`, `app.py:142`, `app.py:178` | Medium | `SELECT *`로 비밀번호·소유권·파일명 등 불필요 필드를 조회·전달해 노출 범위 증가 | 공개 사용자와 공개 상품 모두 명시 SELECT projection과 frozen·slots DTO만 template에 전달한다. 상품은 seller_id/image_filename과 User id/hash/role/status/version/Wallet을 projection에서 제외한다. | Mitigated | 실제 사용자·상품 SQL SELECT 절, DTO field allowlist, route context와 응답 금지 필드 자동 테스트 |
| SEC-18 | `phase-01-foundation:app/__init__.py` user loader | Medium | dormant User는 `None`이었지만 인증 session key가 남아 관리자가 다시 active로 바꾸면 과거 session cookie가 다시 인증될 수 있었다. 비밀번호 변경 뒤 다른 session을 구분할 버전도 없었다. | `User.auth_version`, 로그인 session 버전 저장, loader의 active·exact version 확인과 인증 키 purge를 구현했다. dormant로 anonymous가 된 뒤 active로 복구해도 과거 session은 계속 anonymous이며 password 변경은 다른 client를 무효화한다. | Mitigated | dormant 기존 session 차단, 재활성화 후 부활 방지, version 누락·mismatch, password 변경 후 다른 client 차단 자동 테스트 |
| SEC-19 | Phase 03 설계·구현 검토 | High | 상품 IDOR와 mass assignment로 타인 상품 수정·삭제, 소유자·제재 상태 변경 가능 | current user owner query, 타인/없는 동일 404, form/service field allowlist, active↔sold만 허용, CSRF와 rate limit | Mitigated | 타인 edit/status/delete, 임의 seller/status/image field, hidden/deleted 복구 자동 테스트 |
| SEC-20 | Phase 03 위협 모델·구현 및 사람 최종 검토 | High | 확장자 신뢰, traversal, configured root/file symlink, filesystem TOCTOU·저장 후 변조, polyglot, metadata, animation·decompression bomb, direct URL로 코드·정보 노출 또는 DoS 가능 | bounded decode/verify, upload/read format·dimension·pixel 재검사, 재인코딩·metadata 제거, random filename, root lstat/open/fstat identity, root dir_fd 상대 create/read/remove, 0700/0600, file/DB cleanup, 비공개 image 정책 | Mitigated | 위장·손상·path·bomb·animation·metadata·polyglot, configured root/file symlink·dir_fd·inode mismatch, read-time dimension/pixel, rollback·상태별 image 자동 테스트 |
| SEC-21 | Phase 04 설계 검토 | High | HTTP logout·password 변경·dormant 이후 장시간 Socket이 계속 송수신 가능 | per-app registry, user/version/monotonic snapshot, event·broadcast 전 DB prune, logout/password 즉시 disconnect, dormant/version/age 제거, user cap | Mitigated | logout/password/dormant/version/max-age send·receive·재활성화 자동 테스트 |
| SEC-22 | Phase 04 설계·구현 검토 | High | conversation ID나 room name을 신뢰하면 타인의 1대1 대화·message 접근 가능 | canonical conversation, route/event participant query, server-only room, arbitrary room 미수용, 타인/없는 동일 응답, direct room-only emit | Mitigated | participant/제3자 route·join·send·수신·room scope 자동 테스트 |

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

## 종결 및 추적 원칙

현재 `Partial`인 항목은 대응 업무 route나 service가 구현될 때 요구사항 ID, 자동 테스트,
migration 또는 설정 검증과 함께 재평가한다. 최종 보고서는 Git 이력에서 실제 관련 commit을
조회해 SEC-18~22를 포함한 Finding별 관련 commit hash를 연결하며, 검증 실패나 미구현 범위를
`Mitigated`로 변경하지 않는다. 관련 commit은 최종 보고서 단계에서 Git 이력으로 연결한다.
