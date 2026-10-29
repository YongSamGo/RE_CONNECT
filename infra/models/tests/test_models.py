import copy
import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


warmup = load("warmup")
host = load("check_host")
config = load("check_config")


def model(vram=1, **changes):
    entry = {"name": warmup.MODEL, "digest": warmup.DIGEST, "size_vram": vram}
    entry.update(changes)
    return {"models": [entry]}


class WarmupTests(unittest.TestCase):
    def test_digest_matches_preparation_manifest(self):
        manifest = ROOT.parents[1] / "backend/tools/ollama-manifest.json"
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(), warmup.DIGEST)

    def test_http_rejects_redirect_encoding_and_oversize(self):
        from unittest.mock import MagicMock
        for status, encoding, body in ((302, "identity", b"{}"), (200, "gzip", b"{}"),
                                       (200, "identity", b"x" * (warmup.MAX_BODY + 1)),
                                       (200, "identity", b"[]")):
            connection = MagicMock()
            response = connection.getresponse.return_value
            response.status = status
            response.getheader.return_value = encoding
            response.read.return_value = body
            with patch.object(warmup.http.client, "HTTPConnection", return_value=connection), self.assertRaises(ValueError):
                warmup.request("/api/tags")
            connection.close.assert_called_once()

    def test_warmup_has_no_user_input_or_download(self):
        calls = []
        def call(path, payload=None, timeout=2):
            calls.append((path, payload, timeout))
            return {"done": True} if path == "/api/generate" else model()
        warmup.warmup(call)
        self.assertEqual([c[0] for c in calls], ["/api/tags", "/api/generate", "/api/ps"])
        self.assertEqual(calls[1][1], {"model": "qwen3:4b", "stream": False, "keep_alive": -1,
                                     "options": {"num_ctx": 16384}})

    def test_digest_mismatch_never_loads(self):
        calls = []
        def call(path):
            calls.append(path)
            return model(digest="a" * 64)
        with self.assertRaises(ValueError):
            warmup.warmup(call)
        self.assertEqual(calls, ["/api/tags"])

    def test_gpu_missing_or_malformed_is_not_ready(self):
        for data in ({}, {"models": None}, {"models": [None]}, model(0), model(True), model("1"), model(name="other")):
            with self.subTest(data=data):
                self.assertFalse(warmup.pinned_model(data, require_gpu=True))

    def test_error_body_never_printed(self):
        with patch.object(warmup, "warmup", side_effect=ValueError("private synthetic body")), patch("builtins.print") as output:
            self.assertEqual(warmup.main(), 1)
            output.assert_called_once_with("model warmup failed")

    def test_retry_is_bounded(self):
        with patch.object(warmup.time, "monotonic", side_effect=[0, 61]), patch.object(warmup.time, "sleep") as sleep:
            with self.assertRaises(ValueError):
                warmup.warmup(lambda *a, **kw: (_ for _ in ()).throw(OSError()))
            sleep.assert_not_called()

    def test_unloaded_after_warmup_fails(self):
        def call(path, *a, **kw):
            return model() if path == "/api/tags" else ({"done": True} if path == "/api/generate" else {"models": []})
        with self.assertRaises(ValueError):
            warmup.warmup(call)


class HostTests(unittest.TestCase):
    def test_host_swap_and_core_collector_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sys/kernel").mkdir(parents=True)
            (root / "sys/fs").mkdir(parents=True)
            (root / "swaps").write_text("Filename Type Size Used Priority\n")
            (root / "sys/kernel/core_pattern").write_text("/dev/null\n")
            (root / "sys/fs/suid_dumpable").write_text("0\n")
            self.assertTrue(all(host.checks(root).values()))
            (root / "swaps").write_text("header\n/swapfile file 1024 0 -2\n")
            (root / "sys/kernel/core_pattern").write_text("|/usr/bin/collector")
            (root / "sys/fs/suid_dumpable").write_text("2")
            self.assertFalse(any(host.checks(root).values()))


def valid_config():
    services = {}
    for name, target in (("ollama", "/models"), ("speech", "/app/models"), ("model-warmup", "/run/warmup.py")):
        services[name] = dict(image="example@sha256:" + "a" * 64, user="10001:10001", read_only=True,
            networks={"models": {}}, cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            restart="no", logging={"driver": "none"}, mem_limit=1024, memswap_limit=1024,
            ulimits={"core": {"soft": 0, "hard": 0}}, volumes=[dict(type="bind", target=target,
            read_only=True, bind={"create_host_path": False})])
    services["backend"] = {"networks": {"models": {}}}
    services["ollama"]["environment"] = dict(OLLAMA_NO_CLOUD="1", OLLAMA_KEEP_ALIVE="-1", OLLAMA_NUM_PARALLEL="1",
        OLLAMA_MAX_LOADED_MODELS="1", OLLAMA_CONTEXT_LENGTH="16384")
    services["ollama"]["deploy"] = {"resources": {"reservations": {"devices": [{"driver": "nvidia", "count": 1, "capabilities": ["gpu"]}]}}}
    services["speech"]["deploy"] = copy.deepcopy(services["ollama"]["deploy"])
    services["speech"]["environment"] = {"SPEECH_DEVICE": "cuda"}
    return {"services": services, "networks": {"models": {"internal": True}}}


class ConfigTests(unittest.TestCase):
    def test_valid(self):
        config.validate(valid_config())

    def test_compose_v5_numeric_and_zero_omission(self):
        c = valid_config()
        for name in ("ollama", "speech", "model-warmup"):
            c["services"][name].update(mem_limit="1024", memswap_limit="1024", ulimits={"core": {}})
        config.validate(c)
        c["services"]["ollama"]["ulimits"] = {}
        with self.assertRaises(ValueError):
            config.validate(c)

    def test_unsafe_runtime_settings_rejected(self):
        mutations = [
            lambda c: c["services"]["ollama"].update(image="ollama/ollama:latest"),
            lambda c: c["services"]["speech"].update(ports=[{"published": "8001"}]),
            lambda c: c["services"]["ollama"].update(memswap_limit=2048),
            lambda c: c["services"]["ollama"]["environment"].update(OLLAMA_NO_CLOUD="0"),
            lambda c: c["networks"]["models"].update(internal=False),
            lambda c: c["services"]["speech"]["volumes"][0].update(read_only=False),
            lambda c: c["services"]["speech"].update(logging={"driver": "json-file"}),
            lambda c: c["services"]["ollama"].update(ulimits={"core": {"soft": 1, "hard": 1}}),
            lambda c: c["services"]["ollama"].update(privileged=True),
            lambda c: c["services"]["ollama"].update(networks={"egress": {}}),
        ]
        for mutation in mutations:
            c = copy.deepcopy(valid_config()); mutation(c)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                config.validate(c)


class RenderedComposeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required; daemon not needed")
    def test_effective_production_overlay(self):
        repository = ROOT.parents[1]
        environment = os.environ.copy()
        for key in ("BACKEND_IMAGE", "FRONTEND_IMAGE", "SPEECH_IMAGE", "SPEECH_GPU_IMAGE", "OLLAMA_IMAGE"):
            environment[key] = "example@sha256:" + "a" * 64
        environment.update(AWS_REGION="ap-northeast-2", DEPLOY_ENV="staging",
            OLLAMA_MODELS_DIR=str(repository / "models/ollama"),
            SPEECH_MODELS_DIR=str(repository / "speech/models"),
            OLLAMA_MEMORY_LIMIT="8g", SPEECH_MEMORY_LIMIT="8g", OLLAMA_CPUS="2", SPEECH_CPUS="2")
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / "empty.env"; env.write_text("")
            environment.update(APP_ENV_FILE=str(env), REDIS_ENV_FILE=str(env), MIGRATE_ENV_FILE=str(env))
            result = subprocess.run(["docker", "compose", "--env-file", str(env),
                "-f", "infra/compose.prod.yaml", "-f", "infra/compose.models.yaml",
                "--profile", "model-tools", "config", "--format", "json"],
                cwd=repository, env=environment, capture_output=True, timeout=30, check=True)
        rendered = json.loads(result.stdout)
        config.validate(rendered)
        for name in ("ollama", "speech"):
            self.assertFalse(rendered["services"][name].get("ports"))
            options = rendered["services"][name]["tmpfs"][0]
            for flag in ("noexec", "nosuid", "nodev"):
                self.assertIn(flag, options)
        backend = rendered["services"]["backend"]
        self.assertEqual(backend["memswap_limit"], backend["mem_limit"])
        self.assertTrue(config.zero_core(backend))
        self.assertNotIn("ollama", backend["depends_on"])
        self.assertNotIn("speech", backend["depends_on"])


if __name__ == "__main__":
    unittest.main()
