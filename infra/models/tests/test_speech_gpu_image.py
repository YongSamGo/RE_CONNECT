"""GPU-free regression checks for the restricted speech image's runtime ENV."""

from pathlib import Path
import shlex
import unittest


DOCKERFILE = Path(__file__).resolve().parents[3] / "speech/Dockerfile.gpu"


class SpeechGpuImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = DOCKERFILE.read_text(encoding="utf-8")
        cls.runtime_env = {}
        # Only inspect the final stage: build-stage ENV does not reach the service.
        runtime = source.rsplit("FROM ", 1)[1]
        for line in runtime.replace("\\\n", " ").splitlines():
            if line.startswith("ENV "):
                cls.runtime_env.update(token.split("=", 1) for token in shlex.split(line[4:]))

    def test_native_jit_disabled_without_runtime_compiler(self):
        self.assertEqual(self.runtime_env.get("TORCH_DISABLE_NATIVE_JIT"), "1")

    def test_pytorch_cudnn_precedes_ct2_cublas_without_ct2_cudnn(self):
        self.assertEqual(self.runtime_env.get("LD_LIBRARY_PATH", "").split(":"), [
            "/opt/venv/lib/python3.12/site-packages/nvidia/cudnn/lib",
            "/opt/ct2/nvidia/cublas/lib",
        ])

    def test_home_uses_writable_tmpfs_for_uid_without_home(self):
        self.assertEqual(self.runtime_env.get("HOME"), "/tmp")
