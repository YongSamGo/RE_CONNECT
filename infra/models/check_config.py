"""렌더링한 운영 Compose JSON을 검사한다. env·이미지 주소·본문은 출력하지 않는다."""
import json
from pathlib import Path
import re
import sys


def unsigned(value):
    # Compose v2는 정수, v5는 바이트 수 문자열을 출력한다.
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    raise ValueError("invalid numeric setting")


def zero_core(service):
    limits = service.get("ulimits", {})
    if "core" not in limits:
        return False
    core = limits["core"]
    # v5는 0-valued soft/hard 필드를 JSON에서 생략한다.
    return isinstance(core, dict) and not set(core) - {"soft", "hard"} and all(
        unsigned(core.get(key, 0)) == 0 for key in ("soft", "hard"))


def validate(config, *, allow_local_images=False):
    services = config["services"]
    for name in ("ollama", "speech", "model-warmup"):
        service = services[name]
        image = service["image"]
        pinned = re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image)
        local = allow_local_images and re.fullmatch(r"sha256:[0-9a-f]{64}", image)
        if not pinned and not local:
            raise ValueError("image must use digest")
        if service.get("ports") or service.get("privileged") or service.get("cap_add"):
            raise ValueError("unexpected privilege or port")
        if service.get("network_mode") or set(service["networks"]) != {"models"}:
            raise ValueError("unexpected network")
        if service.get("user") != "10001:10001" or service.get("read_only") is not True:
            raise ValueError("user or filesystem mismatch")
        if set(service.get("cap_drop", [])) != {"ALL"}:
            raise ValueError("capabilities mismatch")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            raise ValueError("privileges mismatch")
        if service.get("logging", {}).get("driver") != "none":
            raise ValueError("persistent logs enabled")
        memory = unsigned(service.get("mem_limit", 0))
        if memory <= 0 or unsigned(service.get("memswap_limit")) != memory:
            raise ValueError("swap or memory mismatch")
        if not zero_core(service):
            raise ValueError("core dump enabled")
        if service.get("restart") != "no":
            raise ValueError("automatic model restart enabled")
        volumes = service.get("volumes", [])
        target = {"ollama": "/models", "speech": "/app/models", "model-warmup": "/run/warmup.py"}[name]
        if len(volumes) != 1 or volumes[0].get("target") != target:
            raise ValueError("unexpected persistent mount")
        mount = volumes[0]
        if mount.get("type") != "bind" or mount.get("read_only") is not True:
            raise ValueError("writable model mount")
        if mount.get("bind", {}).get("create_host_path") is not False:
            raise ValueError("missing paths must fail")
    if config["networks"]["models"].get("internal") is not True:
        raise ValueError("models network must be internal")
    if "models" not in services["backend"]["networks"]:
        raise ValueError("backend missing model network")
    environment = services["ollama"].get("environment", {})
    required = {"OLLAMA_NO_CLOUD": "1", "OLLAMA_KEEP_ALIVE": "-1", "OLLAMA_NUM_PARALLEL": "1",
                "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_CONTEXT_LENGTH": "16384"}
    if any(environment.get(key) != value for key, value in required.items()):
        raise ValueError("model environment mismatch")
    if services["speech"].get("environment", {}).get("SPEECH_DEVICE") != "cuda":
        raise ValueError("speech GPU mode required")
    for name in ("ollama", "speech"):
        devices = services[name]["deploy"]["resources"]["reservations"]["devices"]
        if len(devices) != 1 or devices[0].get("driver") != "nvidia" or devices[0].get("count") != 1 or devices[0].get("capabilities") != ["gpu"]:
            raise ValueError("GPU reservation mismatch")


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError("expected rendered config path")
        validate(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        print("model configuration check failed")
        return 1
    print("model configuration ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
