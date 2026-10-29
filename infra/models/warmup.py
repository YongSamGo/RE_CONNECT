"""고정 모델 사전 적재. 다운로드·입력 본문·상세 예외 출력 없음."""
import http.client
import json
import time

MODEL = "qwen3:4b"
DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"
MAX_BODY = 65536


def request(path, payload=None, timeout=2):
    # 목적지는 고정된 Compose DNS다. proxy·redirect를 사용하지 않는다.
    connection = http.client.HTTPConnection("ollama", 11434, timeout=timeout)
    try:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        connection.request("GET" if body is None else "POST", path, body,
                           {"Content-Type": "application/json", "Accept-Encoding": "identity"})
        response = connection.getresponse()
        if response.status != 200 or response.getheader("Content-Encoding", "identity") != "identity":
            raise ValueError("runtime unavailable")
        data = response.read(MAX_BODY + 1)
        if len(data) > MAX_BODY:
            raise ValueError("response too large")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("invalid response")
        return result
    finally:
        connection.close()


def pinned_model(data, require_gpu=False):
    models = data.get("models")
    if not isinstance(models, list):
        return False
    for model in models:
        if not isinstance(model, dict):
            continue
        if model.get("name") != MODEL or model.get("digest") != DIGEST:
            continue
        vram = model.get("size_vram")
        if require_gpu and (type(vram) is not int or vram <= 0):
            continue
        return True
    return False


def warmup(call=request):
    # 시작 대기는 최대 60초. 모델 불일치는 즉시 실패하고 pull하지 않는다.
    deadline = time.monotonic() + 60
    while True:
        try:
            tags = call("/api/tags")
            break
        except (OSError, ValueError, http.client.HTTPException):
            if time.monotonic() >= deadline:
                raise ValueError("runtime unavailable") from None
            time.sleep(2)
    if not pinned_model(tags):
        raise ValueError("model mismatch")
    result = call("/api/generate", {"model": MODEL, "stream": False, "keep_alive": -1,
                                  "options": {"num_ctx": 16384}}, timeout=180)
    if result.get("done") is not True or not pinned_model(call("/api/ps"), require_gpu=True):
        raise ValueError("model not loaded on GPU")


def main():
    try:
        warmup()
    except (OSError, ValueError, http.client.HTTPException):
        print("model warmup failed")
        return 1
    print("model ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
