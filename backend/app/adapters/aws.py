"""AWS SDK 클라이언트 생성. 자격 증명은 EC2 인스턴스 역할에서 읽고 설정·코드에 두지 않는다."""

import boto3
from botocore.config import Config

# 삭제 이력 쓰기는 사용자 요청 처리 중 DB 잠금을 잡은 채 실행하므로 오래 기다리지 않는다.
_CLIENT_CONFIG = Config(connect_timeout=2, read_timeout=5, retries={'max_attempts': 3, 'mode': 'standard'})


def build_client(service: str, region: str):
    if service not in {'s3', 'rds'}:
        raise ValueError(service)
    return boto3.session.Session().client(service, region_name=region, config=_CLIENT_CONFIG)
