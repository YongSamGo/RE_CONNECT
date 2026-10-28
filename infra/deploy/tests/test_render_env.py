"""render_env.py 정상·공격 입력 시험. 저장소 루트에서 python -m unittest discover -s infra/deploy/tests"""

import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import render_env  # noqa: E402

APP = "/re-connect/production/app/"
# 시험 전용 가짜 값이다. 실제 비밀값이 아니다.
DB = "postgresql+psycopg://runtime:fake@db.internal:5432/reconnect?sslmode=verify-full&sslrootcert=/run/rds-ca.pem"
FAKE_SECRET = "fake-secret-value-for-test"


def parameter(name: str, value: str, kind: str = "SecureString") -> dict[str, str]:
    return {"Name": name, "Value": value, "Type": kind}


def app_document(**overrides: str) -> dict[str, list[dict[str, str]]]:
    values = {
        "DATABASE_URL": DB,
        "REDIS_URL": "redis://:" + "0" * 32 + "@redis:6379/0",
        "REQUEST_LIMIT_KEY": "1" * 64,
        "PUBLIC_ORIGIN": "https://reconnect.example",
        "DATA_ENCRYPTION_KEYS": '{"k1":"' + "A" * 43 + '="}',
        "DATA_ENCRYPTION_ACTIVE_KEY_ID": "k1",
        **overrides,
    }
    return {"Parameters": [parameter(APP + key, value) for key, value in values.items()]}


@unittest.skipIf(os.name == "nt", "POSIX 권한 검사")
class RenderEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        os.chmod(self.root, 0o700)
        self.output = self.root / "app.env"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def run_main(self, document: object, role: str = "app", prefix: str = APP) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = render_env.main(
                ["--role", role, "--prefix", prefix, "--output", str(self.output)],
                stdin=io.StringIO(json.dumps(document)),
            )
        return code, out.getvalue(), err.getvalue()

    def test_writes_private_file_with_raw_values(self) -> None:
        document = app_document(CONSENT_NOTICES_JSON='{"t":"it\'s $HOME ${X}"}')
        code, out, err = self.run_main(document)
        self.assertEqual(code, 0, err)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        lines = self.output.read_text(encoding="utf-8").splitlines()
        self.assertIn('CONSENT_NOTICES_JSON={"t":"it\'s $HOME ${X}"}', lines)
        self.assertIn(f"DATABASE_URL={DB}", lines)
        self.assertNotIn("fake", out + err)
        self.assertEqual(list(self.root.iterdir()), [self.output])

    def test_replaces_existing_file_atomically(self) -> None:
        self.output.write_text("OLD=1\n", encoding="utf-8")
        self.assertEqual(self.run_main(app_document())[0], 0)
        self.assertNotIn("OLD=1", self.output.read_text(encoding="utf-8"))

    def test_rejects_newline_injection_without_writing(self) -> None:
        for value in (FAKE_SECRET + "\nAPP_ENV=development", FAKE_SECRET + "\r", "a\0b", ""):
            with self.subTest(value=value):
                code, out, err = self.run_main(app_document(KAKAO_CLIENT_SECRET=value))
                self.assertEqual(code, 1)
                self.assertFalse(self.output.exists())
                self.assertNotIn(FAKE_SECRET, out + err)

    def test_rejects_names_outside_allowlist(self) -> None:
        for extra in ("APP_ENV", "TRUSTED_PROXY_IPS", "OLLAMA_BASE_URL", "LD_PRELOAD", "../migrate/DATABASE_URL"):
            with self.subTest(extra=extra):
                document = app_document()
                document["Parameters"].append(parameter(APP + extra, "x"))
                self.assertEqual(self.run_main(document)[0], 1)
                self.assertFalse(self.output.exists())

    def test_rejects_other_prefix_and_role_mismatch(self) -> None:
        document = app_document()
        document["Parameters"].append(parameter("/re-connect/production/migrate/DATABASE_URL", DB))
        self.assertEqual(self.run_main(document)[0], 1)
        self.assertEqual(self.run_main(app_document(), role="migrate", prefix=APP)[0], 1)
        self.assertEqual(self.run_main(app_document(), prefix="/other/app/")[0], 1)

    def test_rejects_plain_string_duplicates_and_missing(self) -> None:
        plain = app_document()
        plain["Parameters"][0]["Type"] = "String"
        duplicate = app_document()
        duplicate["Parameters"].append(parameter(APP + "PUBLIC_ORIGIN", "https://evil.example"))
        missing = app_document()
        missing["Parameters"] = [p for p in missing["Parameters"] if not p["Name"].endswith("REQUEST_LIMIT_KEY")]
        for document in (plain, duplicate, missing, {"Parameters": "x"}, []):
            with self.subTest(document=str(document)[:40]):
                self.assertEqual(self.run_main(document)[0], 1)
                self.assertFalse(self.output.exists())

    def test_database_url_requires_verified_tls(self) -> None:
        for url in (
            DB.replace("verify-full", "require"),
            DB.split("?")[0],
            DB.replace("/run/rds-ca.pem", "/tmp/ca.pem"),
            DB + "&sslmode=disable",
            DB.replace("postgresql+psycopg", "postgresql"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.run_main(app_document(DATABASE_URL=url))[0], 1)

    def test_redis_values(self) -> None:
        self.assertEqual(self.run_main(app_document(REDIS_URL="redis://:pw@evil.example:6379/0"))[0], 1)
        redis_prefix = "/re-connect/production/redis/"
        self.output = self.root / "redis.env"
        good = {"Parameters": [parameter(redis_prefix + "REDIS_PASSWORD", "a" * 32)]}
        self.assertEqual(self.run_main(good, role="redis", prefix=redis_prefix)[0], 0)
        for bad in ("a" * 31, "g" * 32, "a" * 32 + " requirepass x"):
            with self.subTest(bad=bad):
                document = {"Parameters": [parameter(redis_prefix + "REDIS_PASSWORD", bad)]}
                self.assertEqual(self.run_main(document, role="redis", prefix=redis_prefix)[0], 1)

    def test_refuses_shared_writable_directory_and_symlink(self) -> None:
        # 그룹 쓰기만 열어도 거절해야 한다. 기타 쓰기는 같은 검사 비트라 따로 열지 않는다.
        os.chmod(self.root, 0o770)
        self.assertEqual(self.run_main(app_document())[0], 1)
        os.chmod(self.root, 0o700)
        target = self.root / "elsewhere"
        target.write_text("keep\n", encoding="utf-8")
        self.output.symlink_to(target)
        self.assertEqual(self.run_main(app_document())[0], 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep\n")


if __name__ == "__main__":
    unittest.main()
