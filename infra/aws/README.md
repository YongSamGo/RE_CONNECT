# EC2·비공개 RDS 구성 (#90)

`network.yaml`은 CloudFormation 구성 코드다. 배포·실환경 검증은 아직 하지 않았다.
인터넷 경로는 애플리케이션 서브넷에만 있고, DB는 두 가용 영역의 별도 서브넷에 둔다.
DB 포트는 애플리케이션 보안 그룹에서만 허용한다. SSH·Redis·추론 포트는 공개하지 않는다.
RDS 비밀번호는 RDS가 Secrets Manager에서 관리하며 템플릿·출력에 넣지 않는다.

AWS 계정·할당량·비용 승인이 준비된 뒤 사람이 change set을 검토하고 배포한다.
`ImageId`는 대상 리전에서 검증한 x86_64 AMI를 지정해야 한다. AMI의 루트 장치는
`/dev/xvda`여야 하며 애플리케이션·TLS 인증서·업데이트·복구 접근은 별도로 구성한다.
이 구성에는 관리 IAM 역할이나 마스터 비밀번호 조회 권한을 부여하지 않는다.
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

이 폴더의 도구는 Python 3.12를 사용한다. 로컬 테스트에는 PyYAML·cryptography가 필요하다.
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
3. `reconnect_migrator`로 마이그레이션을 실행한 뒤 같은 계정으로
   `grant_runtime.sql`을 실행한다. 소유자가 다른 테이블이 있으면 권한 적용을 중단한다.
   신규 테이블에는 자동 권한을 부여하지 않으므로 매 마이그레이션 후 다시 실행한다.
4. 애플리케이션은 `reconnect_runtime`만 사용한다. 실행 계정은 마이그레이션 역할의
   멤버가 아니며 CREATE·TRUNCATE·GRANT 권한 및 `alembic_version` 접근 권한이 없다.
   TLS 연결로 정상 DML 성공과 DDL·마이그레이션 테이블 변경 거절을 실제 확인한다.

SQL은 아직 실제 PostgreSQL/RDS에서 실행하지 않았다. 기존 DB 적용·공개 스키마 내
추가 테이블/시퀀스·DB 계정 회전·백업 복구 후 권한은 운영 전 별도로 검증한다.

공식 근거:

- [RDS TLS와 force_ssl](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html)
- [RDS 비밀번호 관리](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html)
