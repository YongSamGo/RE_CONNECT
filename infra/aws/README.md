# EC2·비공개 RDS 구성 (#90)

`network.yaml`은 CloudFormation 구성 코드다. 배포·실환경 검증은 아직 하지 않았다.
인터넷 경로는 애플리케이션 서브넷에만 있고, DB는 두 가용 영역의 별도 서브넷에 둔다.
DB 포트는 애플리케이션 보안 그룹에서만 허용한다. SSH·Redis·추론 포트는 공개하지 않는다.
RDS 비밀번호는 RDS가 Secrets Manager에서 관리하며 템플릿·출력에 넣지 않는다.

AWS 계정·할당량·비용 승인이 준비된 뒤 사람이 change set을 검토하고 배포한다.
`ImageId`는 대상 리전에서 검증한 x86_64 AMI를 지정해야 한다. AMI의 루트 장치는
`/dev/xvda`여야 하며 애플리케이션·TLS 인증서·업데이트·복구 접근은 별도로 구성한다.
이 구성에는 관리 IAM 역할이나 마스터 비밀번호 조회 권한을 부여하지 않는다.
최소 권한 애플리케이션 DB 계정과 마이그레이션 계정 생성은 별도 단계다.
EC2·RDS·스토리지·백업·Secrets Manager·공인 IPv4는 배포 시 비용이 발생한다.

RDS 서버는 `rds.force_ssl=1`로 비암호화 연결을 거절한다.
클라이언트는 AWS 공식 RDS CA 번들과 실제 DB 엔드포인트를 사용해
`sslmode=verify-full`을 설정해야 한다. IP 주소나 검증 비활성 옵션으로 대체하지 않는다.
배포 후 정상 인증서 연결 성공, 잘못된 CA·호스트 및 `sslmode=disable` 연결 실패,
EC2 외 호스트에서 DB 접속 실패를 확인하기 전에는 #90 완료로 판정하지 않는다.
백업은 7일 보관하며 삭제 보호와 삭제·교체 시 스냅샷 보존을 설정했다.

오프라인 회귀 검사: 저장소 루트에서 `python -m unittest discover -s infra/aws/tests`.
CloudFormation 스키마 검사는 `cfn-lint infra/aws/network.yaml`을 사용한다.

공식 근거:

- [RDS TLS와 force_ssl](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html)
- [RDS 비밀번호 관리](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html)
