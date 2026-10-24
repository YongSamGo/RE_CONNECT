"""모델 준비의 정상·변조·경로·부분 다운로드 경계. 네트워크/실모델 불필요."""

import hashlib
import io
from pathlib import Path
import urllib.request

import pytest

from tools import prepare_ollama as prep


@pytest.fixture
def model(monkeypatch):
    raw = b'{"fixture": true}'
    bodies = [b"config", b"GGUFfixture"]
    entries = [{"size": len(b), "digest": "sha256:" + hashlib.sha256(b).hexdigest()} for b in bodies]
    monkeypatch.setattr(prep, "MANIFEST_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(prep, "pinned_manifest", lambda: (raw, entries))
    return raw, bodies, entries


class Response(io.BytesIO):
    status = 200
    headers = {}


def fake_registry(monkeypatch, model):
    _, bodies, entries = model
    sources = {prep.REGISTRY + e["digest"]: b for e, b in zip(entries, bodies, strict=True)}
    monkeypatch.setattr(prep, "open_blob", lambda url: Response(sources[url]))


def test_pinned_production_manifest():
    raw, entries = prep.pinned_manifest()
    assert len(entries) == 5
    assert len(raw) == 859
    assert entries[1]["size"] == 2497280480
    assert entries[1]["digest"] == "sha256:3e4cb14174460404e7a233e531675303b2fbf7749c02f91864fe311ab6344e4f"


def test_tampered_manifest_is_not_trusted(tmp_path, monkeypatch):
    path = tmp_path / "manifest"
    path.write_bytes(b"{}")
    monkeypatch.setattr(prep, "MANIFEST_FILE", path)
    with pytest.raises(prep.PreparationError):
        prep.prepare(tmp_path / "models")
    assert not (tmp_path / "models").exists()


def test_prepare_and_offline_verify_and_idempotence(tmp_path, monkeypatch, model):
    fake_registry(monkeypatch, model)
    prep.prepare(tmp_path)
    assert (tmp_path / prep.MANIFEST_PATH).read_bytes() == model[0]
    assert not list(tmp_path.rglob(".prepare-*"))
    monkeypatch.setattr(prep, "open_blob", lambda _: pytest.fail("network must not be used"))
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: pytest.fail("offline verify"))
    prep.verify(tmp_path)
    prep.prepare(tmp_path)


@pytest.mark.parametrize("body", [b"", b"bad-data", b"too many bytes", b"GGUFfixturE"])
def test_invalid_download_does_not_publish(tmp_path, monkeypatch, model, body):
    monkeypatch.setattr(prep, "open_blob", lambda _: Response(body))
    with pytest.raises(prep.PreparationError):
        prep.prepare(tmp_path)
    assert not (tmp_path / prep.MANIFEST_PATH).exists()
    assert not list(tmp_path.rglob(".prepare-*"))
    assert not list(tmp_path.rglob("sha256-*"))


def test_partial_download_can_retry_without_manifest(tmp_path, monkeypatch, model):
    raw, bodies, entries = model
    def interrupted(url):
        if url.endswith(entries[1]["digest"]):
            raise OSError("signed URL and secret must not be printed")
        return Response(bodies[0])
    monkeypatch.setattr(prep, "open_blob", interrupted)
    with pytest.raises(OSError):
        prep.prepare(tmp_path)
    assert not (tmp_path / prep.MANIFEST_PATH).exists()
    assert len(list((tmp_path / "blobs").iterdir())) == 1
    fake_registry(monkeypatch, model)
    prep.prepare(tmp_path)
    assert (tmp_path / prep.MANIFEST_PATH).read_bytes() == raw


def test_existing_corrupt_file_is_not_replaced(tmp_path, monkeypatch, model):
    fake_registry(monkeypatch, model)
    prep.prepare(tmp_path)
    blob = next((tmp_path / "blobs").iterdir())
    blob.write_bytes(b"tampered")
    with pytest.raises(prep.PreparationError):
        prep.verify(tmp_path)
    with pytest.raises(prep.PreparationError):
        prep.prepare(tmp_path)
    assert blob.read_bytes() == b"tampered"


def test_preexisting_lock_is_preserved(tmp_path, monkeypatch, model):
    fake_registry(monkeypatch, model)
    lock = tmp_path / ".prepare-lock"
    lock.mkdir()
    with pytest.raises(prep.PreparationError):
        prep.prepare(tmp_path)
    assert lock.is_dir()


@pytest.mark.parametrize("url", [
    "http://registry.ollama.ai/v2/x", "file:///etc/passwd", "https://127.0.0.1/x",
    "https://registry.ollama.ai.attacker.invalid/x", "https://user@registry.ollama.ai/x",
    "https://registry.ollama.ai:444/x", "https://registry.ollama.ai/x#fragment",
    "https://registry.ollama.ai\\@attacker.invalid/x",
])
def test_untrusted_download_or_redirect_url_rejected(url):
    with pytest.raises(prep.PreparationError):
        prep.validate_url(url)
    with pytest.raises(prep.PreparationError):
        prep.RegistryRedirect().redirect_request(None, None, 307, "", {}, url)


def test_redirect_to_observed_https_cdn_allowed():
    prep.validate_url("https://registry.ollama.ai/v2/library/qwen3/blobs/sha256:abc")
    prep.validate_url("https://dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com/opaque?signature=fixture")


@pytest.mark.parametrize("encoding,length", [("gzip", None), ("identity", "999")])
def test_bad_download_headers_rejected(tmp_path, monkeypatch, model, encoding, length):
    def response(_):
        result = Response(model[1][0])
        result.headers = {"Content-Encoding": encoding}
        if length is not None:
            result.headers["Content-Length"] = length
        return result
    monkeypatch.setattr(prep, "open_blob", response)
    with pytest.raises(prep.PreparationError):
        prep.prepare(tmp_path)
    assert not (tmp_path / prep.MANIFEST_PATH).exists()


def test_no_overwrite_on_publish(tmp_path):
    destination = tmp_path / "existing"
    destination.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        prep.publish(io.BytesIO(b"new"), destination, 3, hashlib.sha256(b"new").hexdigest())
    assert destination.read_bytes() == b"keep"
    assert not list(tmp_path.glob(".prepare-*"))


def test_interrupted_stream_cleans_only_own_temporary(tmp_path):
    class BrokenStream:
        calls = 0

        def read(self, _):
            self.calls += 1
            if self.calls > 1:
                raise OSError("network interrupted")
            return b"part"

    preserved = tmp_path / ".prepare-other-owner"
    preserved.write_bytes(b"keep")
    destination = tmp_path / "blob"
    with pytest.raises(OSError):
        prep.publish(BrokenStream(), destination, 8, hashlib.sha256(b"partpart").hexdigest())
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == [preserved]


def test_symlink_root_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("OS requires privilege for symlink creation")
    with pytest.raises(prep.PreparationError):
        prep.prepare(link / "child")
    assert list(target.iterdir()) == []


def test_hardlink_blob_rejected(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"data")
    link = tmp_path / "link"
    link.hardlink_to(source)
    with pytest.raises(prep.PreparationError):
        prep.verify_file(link, 4, hashlib.sha256(b"data").hexdigest())


def test_cli_hides_external_exception(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prepare_ollama.py", "prepare", "--root", str(tmp_path)])
    def fail(_):
        raise OSError("signed URL secret fixture")
    monkeypatch.setattr(prep, "prepare", fail)
    assert prep.main() == 1
    assert "secret" not in capsys.readouterr().out
