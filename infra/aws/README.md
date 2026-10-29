# EC2·비공개 RDS 구성 (#90)

`network.yaml`은 CloudFormation 구성 코드다. 배포·실환경 검증은 아직 하지 않았다.
인터넷 경로는 애플리케이션 서브넷에만 있고, DB는 두 가용 영역의 별도 서브넷에 둔다.
DB 포트는 애플리케이션 보안 그룹에서만 허용한다. SSH·Redis·추론 포트는 공개하지 않는다.
RDS 비밀번호는 RDS가 Secrets Manager에서 관리하며 템플릿·출력에 넣지 않는다.

AWS 계정·할당량·비용 승인이 준비된 뒤 사람이 change set을 검토하고 배포한다.
`ImageId`는 대상 리전에서 검증한 x86_64 AMI를 지정해야 한다. AMI의 루트 장치는
`/dev/xvda`이고 패키지 저장소가 HTTPS여야 한다. 애플리케이션·TLS 인증서·업데이트는
별도로 구성한다. 검토한 기존 인스턴스 프로파일 이름을 `InstanceProfileName`으로 받는다.
프로파일에는 Session Manager, ECR pull, 앱용 비밀값 읽기, 로그 쓰기, 삭제 이력 S3의
최소 범위 권한만 부여한다([배포 권한 기준](../deploy/README.md)). 관리용 DB 마스터
비밀번호 조회 권한은 부여하지 않는다. SSH는 열지 않고 Session Manager를 사용한다.
컨테이너의 IMDSv2 응답을 위해 hop limit은 2, 토큰은 필수다. 배포 시 호스트 방화벽에서
backend만 메타데이터에 접근하게 제한하고 nginx·모델·음성 컨테이너의 차단을 확인해야 한다.
탄력적 IP를 EC2에 연결하고 `PublicAddress`로 반환한다. 도메인의 A 레코드는 이 주소로
연결하며 실제 운영 스택에 적용하기 전 운영 사본과 change set 차이를 사람이 확인한다.
DB 계정 초기화는 아래 SQL로 분리한다. EC2에 마스터 계정을 제공하지 않는다.
EC2·RDS·스토리지·백업·Secrets Manager·공인 IPv4는 배포 시 비용이 발생한다.

RDS 서버는 `rds.force_ssl=1`로 비암호화 연결을 거절한다.
클라이언트는 AWS 공식 RDS CA 번들과 실제 DB 엔드포인트를 사용해
`sslmode=verify-full`을 설정해야 한다. IP 주소나 검증 비활성 옵션으로 대체하지 않는다.
배포 후 정상 인증서 연결 성공, 잘못된 CA·호스트 및 `sslmode=disable` 연결 실패,
EC2 외 호스트에서 DB 접속 실패를 확인하기 전에는 #90 완료로 판정하지 않는다.
백업은 7일 보관하며 삭제 보호와 삭제·교체 시 스냅샷 보존을 설정했다.

오프라인 회귀 검사: 저장소 루트에서 `python -m unittest discover -s infra/aws/tests`.
CloudFormation 스키마 검사는 `cfn-lint infra/aws/network.yaml`을 사용한다.

## DB 계정과 TLS 사전 검사

이 폴더의 도구는 Python 3.12를 사용한다. 테스트의 cryptography·psycopg는
해시 고정 `backend/requirements.txt`를 사용하고 PyYAML은 이 폴더의
`requirements-dev.txt`로 버전·배포물 해시를 고정한다. PyYAML 해시는 공식 PyPI
6.0.3 릴리스 JSON의 SHA-256 목록이며 입력 버전은 `requirements-dev.in`에 둔다.
CI backend 잡에서 AWS 테스트·TLS 도구 Bandit·추가 의존성 pip-audit를 실행한다.
별도 PostgreSQL 16 Unix socket 클러스터를 만들어 비슈퍼유저 초기화·SQL 권한 시험도 실행한다.
운영 도구 `check_database_tls.py` 자체는 표준 라이브러리만 사용한다.

```bash
python infra/aws/check_database_tls.py --host <RDS-DNS-endpoint> --ca-file <AWS-CA-bundle.pem>
```

이 명령은 실제 PostgreSQL TLS 협상을 하고 CA·호스트명을 검증한다. 자격증명을
받지 않으며 DB 로그인·SQL 권한·평문 접속 거절을 증명하지 않는다.
검증 실패 시 종료 코드는 1이고 상세 연결 정보는 출력하지 않는다.

1. 새 `reconnect` DB에서 RDS 관리자 계정으로 `bootstrap_database.sql`을 실행한다.
   psql은 `-X`로 사용자 시작 설정을 배제하고, `PGSSLMODE=verify-full`,
   `PGSSLROOTCERT=<AWS CA 경로>`, `PGGSSENCMODE=disable`을 설정한다.
   비밀번호는 명령줄·연결 URL·로그에 넣지 않고 보호된 passfile을 사용한다.
   기존 역할이 있으면 전체 트랜잭션이 실패하며 알 수 없는 기존 권한을 재사용하지 않는다.
2. 두 계정의 비밀번호를 비밀 관리 경로에서 준비한다. 대화형 psql의 `\password`로
   설정하고 각 역할을 `LOGIN`으로 전환한다. 저장소에는 비밀번호를 기록하지 않는다.
   초기화 스크립트는 비밀번호 없는 로그인 역할을 자동으로 열지 않는다.
3. 첫 마이그레이션 전에 `reconnect_migrator` 본인으로 `grant_runtime.sql`을 실행해
   함수의 PUBLIC 기본 실행 권한을 제거한다. 마이그레이션 뒤에도 같은 계정으로
   `grant_runtime.sql`을 실행한다. 기존 함수의 PUBLIC 실행 권한도 회수하고,
   소유자가 다른 테이블·함수가 있으면 권한 적용을 중단한다.
   신규 테이블에는 자동 권한을 부여하지 않으므로 매 마이그레이션 후 다시 실행한다.
4. 애플리케이션은 `reconnect_runtime`만 사용한다. 실행 계정은 마이그레이션 역할의
   멤버가 아니며 CREATE·TRUNCATE·GRANT 권한이 없다. `alembic_version`은 읽기만 할 수 있다.
   복원 후 공개 전 확인(`restore-check`, #95)이 복원 DB의 스키마 버전을 대조하는 데 필요하고,
   쓰기·삭제·비우기는 계속 거절된다.
   TLS 연결로 정상 DML 성공과 DDL·마이그레이션 테이블 변경 거절을 실제 확인한다.

기존 전용 Unix socket PostgreSQL 16 시험은 초기 NOLOGIN·상승 권한 없음,
실제 실행 계정의 DML/시퀀스 사용, DDL·TRUNCATE·마이그레이션 테이블 변경·소유자 함수 접근과
역할 승격 거절을 확인했다. 새 테이블의 자동 권한 부여 없음, 명시적 재적용, 다른 소유자
객체가 있을 때 권한 전체 롤백, 초기화 재실행 시 기존 역할 보존도 확인했다.

역할 시험은 `DB_ROLE_TEST_SOCKET`이 명시된 새 `/tmp/reconnect-db-roles-.../socket`
클러스터에서만 실행한다. 실제 서버의 data_directory·포트·TCP listen 비활성·버전·기존 역할
없음을 검사하며 `reconnect` DB/역할을 만들거나 수정하므로 운영 DB에는 사용할 수 없다.
psycopg와 psql이 필요하고, 시험 클러스터는 별도로 준비·종료해야 한다.
변수 없이 일반 오프라인 시험을 돌리면 역할 시험은 제외된다.

추가 회귀는 DB 소유자인 `CREATEROLE NOSUPERUSER NOINHERIT` 관리자로 초기화하고,
기존·미래 함수의 PUBLIC 실행 거절 및 다른 함수 소유자의 원자적 실패도 확인한다.
로컬 Windows에서는 Unix socket 역할 시험을 건너뛰며 실제 실행 결과는 해당 CI 단계를 확인한다.

이 증거는 로컬 trust 인증의 별도 클러스터에서 얻었다. RDS 배포·실제 자격 증명·TLS를
사용한 역할 접속은 검증하지 않았다. 기존 DB 적용·공개 스키마 내 추가 테이블/시퀀스·
별도 관리 작업 역할·계정 회전·백업 복구 후 권한은 운영 전 별도로 검증한다.

공식 근거:

- [RDS TLS와 force_ssl](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html)
- [RDS 비밀번호 관리](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html)
