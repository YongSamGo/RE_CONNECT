"""실행 중인 개발 컨테이너의 실제 마운트·포트·네트워크를 확인한다.

docker inspect 전체에는 환경 비밀값이 있으므로 원문을 출력하지 않는다.
저장소 루트에서 python infra/check_dev_services.py로 실행한다.
"""

import json
import subprocess


def docker(*arguments):
    return subprocess.run(["docker", *arguments], check=True, capture_output=True, text=True).stdout


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    for service, port, destination in (("postgres", "5432/tcp", "/var/lib/postgresql/data"), ("redis", "6379/tcp", "/data")):
        container_id = docker("compose", "--env-file", ".env.example", "-f", "infra/compose.dev.yaml", "ps", "-q", service).strip()
        require(bool(container_id), "Development service is missing")
        container = json.loads(docker("inspect", container_id))[0]
        require(container["State"]["Health"]["Status"] == "healthy", "Development service is unhealthy")
        mounts = container["Mounts"]
        require(any(item["Destination"] == destination and item["Type"] == "tmpfs" for item in mounts), "Development data must use tmpfs")
        require(all(item["Type"] != "volume" for item in mounts), "Persistent data volume is present")
        bindings = container["NetworkSettings"]["Ports"].get(port)
        require(bindings and all(item["HostIp"] == "127.0.0.1" for item in bindings), "Development port must bind loopback")
        require(container["HostConfig"]["LogConfig"]["Type"] == "none", "Container file logging must be disabled")
        networks = [json.loads(docker("network", "inspect", network_id))[0] for network_id in container["NetworkSettings"]["Networks"]]
        require(any(item["Internal"] for item in networks), "Internal data network is missing")
    print("Development services: tmpfs, no persistent volumes/logs, loopback ports and internal data network verified")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        print("Development service verification failed; inspect configuration locally without sharing secrets")
        raise SystemExit(1) from None
