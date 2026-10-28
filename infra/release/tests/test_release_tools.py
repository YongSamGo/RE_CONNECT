"""릴리스 manifest·이미지 검사 판정 시험. 저장소 루트에서 python -m unittest discover -s infra/release/tests"""

import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_image_scan  # noqa: E402
import release_manifest  # noqa: E402

COMMIT = "a" * 40
DIGEST = "@sha256:" + "b" * 64
IMAGES = {
    "backend": "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/reconnect-backend" + DIGEST,
    "frontend": "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/reconnect-frontend" + DIGEST,
    "speech": "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/reconnect-speech" + DIGEST,
}
TODAY = dt.date(2026, 10, 28)


class ReleaseManifestTest(unittest.TestCase):
    def test_build_records_versions_from_repository(self) -> None:
        manifest = release_manifest.build(release_manifest.ROOT, "v0.1.0", COMMIT, IMAGES, {})
        self.assertEqual(manifest["images"], IMAGES)
        self.assertEqual(len(manifest["migrations"]["heads"]), 1)
        self.assertEqual(manifest["prompts"]["generation"], "grounded-v1")
        self.assertEqual(set(manifest["lockfiles"]), set(release_manifest.LOCKFILES))
        for refs in manifest["base_images"].values():
            self.assertTrue(refs and all("@sha256:" in ref for ref in refs))
        self.assertNotIn("password", json.dumps(manifest).lower())

    def test_build_rejects_tags_and_unpinned_references(self) -> None:
        bad_refs = (
            IMAGES["backend"].split("@")[0] + ":latest",
            IMAGES["backend"].replace("b" * 64, "B" * 64),
            IMAGES["backend"] + "\nFRONTEND_IMAGE=evil/x" + DIGEST,
            "evil.example/x" + DIGEST + " ; rm -rf /",
        )
        for ref in bad_refs:
            with self.subTest(ref=ref), self.assertRaises(release_manifest.ManifestError):
                release_manifest.build(release_manifest.ROOT, "v0.1.0", COMMIT, {**IMAGES, "backend": ref}, {})
        for tag, commit in (("main", COMMIT), ("v1.0", COMMIT), ("v1.0.0", "abc"), ("v1.0.0\n", COMMIT)):
            with self.subTest(tag=tag), self.assertRaises(release_manifest.ManifestError):
                release_manifest.build(release_manifest.ROOT, tag, commit, IMAGES, {})
        with self.assertRaises(release_manifest.ManifestError):
            release_manifest.build(release_manifest.ROOT, "v0.1.0", COMMIT, {"backend": IMAGES["backend"]}, {})

    def test_images_env_round_trip_and_tampered_manifest(self) -> None:
        manifest = release_manifest.build(release_manifest.ROOT, "v0.1.0", COMMIT, IMAGES, {})
        text = release_manifest.images_env(manifest)
        self.assertEqual(text.splitlines()[0], "BACKEND_IMAGE=" + IMAGES["backend"])
        self.assertEqual(len(text.splitlines()), 3)
        for images in ({**IMAGES, "backend": "x:latest"}, {**IMAGES, "extra": IMAGES["backend"]}, {}):
            with self.subTest(images=images), self.assertRaises(release_manifest.ManifestError):
                release_manifest.images_env({**manifest, "images": images})
        with self.assertRaises(release_manifest.ManifestError):
            release_manifest.images_env({**manifest, "schema": 2})

    def test_dockerfile_without_digest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Dockerfile"
            path.write_text("FROM python:3.12-slim AS build\n", encoding="utf-8")
            with self.assertRaises(release_manifest.ManifestError):
                release_manifest.base_images(path)

    def test_migration_heads_detects_branches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text('revision = "a"\ndown_revision = None\n', encoding="utf-8")
            (root / "b.py").write_text('revision = "b"\ndown_revision = "a"\n', encoding="utf-8")
            (root / "c.py").write_text('revision = "c"\ndown_revision = "a"\n', encoding="utf-8")
            self.assertEqual(release_manifest.migration_heads(root), ["b", "c"])
            (root / "d.py").write_text('revision = "d"\ndown_revision = ("b", "c")\n', encoding="utf-8")
            self.assertEqual(release_manifest.migration_heads(root), ["d"])


def vulnerability(vid: str, severity: str, fixed: str = "", package: str = "pkg") -> dict[str, str]:
    return {"VulnerabilityID": vid, "PkgName": package, "Severity": severity, "FixedVersion": fixed}


def scan(*items: dict[str, str]) -> dict[str, object]:
    return {"Results": [{"Target": "x", "Vulnerabilities": list(items)}]}


def accept(*entries: dict[str, str]) -> dict[str, object]:
    return {"accepted": list(entries)}


def entry(vid: str, image: str = "speech", recorded: str = "2026-10-20", expires: str = "2026-12-31") -> dict[str, str]:
    return {"id": vid, "image": image, "reason": "수정판 없음, 내부 네트워크 전용이라 노출 경로 없음",
            "recorded": recorded, "expires": expires}


class ImageScanJudgeTest(unittest.TestCase):
    def judge(self, scan_document: object, accept_document: object, image: str = "speech") -> list[str]:
        return check_image_scan.judge(scan_document, accept_document, image, TODAY)[0]

    def test_clean_and_low_findings_pass(self) -> None:
        self.assertEqual(self.judge({"Results": []}, accept()), [])
        self.assertEqual(self.judge(scan(vulnerability("CVE-2026-0001", "MEDIUM", "1.2")), accept()), [])

    def test_critical_always_fails_even_if_accepted(self) -> None:
        document = scan(vulnerability("CVE-2026-0002", "CRITICAL"))
        self.assertTrue(self.judge(document, accept(entry("CVE-2026-0002"))))

    def test_fixable_high_fails_and_unfixed_high_needs_review(self) -> None:
        self.assertTrue(self.judge(scan(vulnerability("CVE-2026-0003", "HIGH", "2.0")), accept(entry("CVE-2026-0003"))))
        unfixed = scan(vulnerability("CVE-2026-0004", "HIGH"))
        self.assertTrue(self.judge(unfixed, accept()))
        self.assertEqual(self.judge(unfixed, accept(entry("CVE-2026-0004"))), [])
        # 다른 이미지에 대한 수용은 적용하지 않는다.
        self.assertTrue(self.judge(unfixed, accept(entry("CVE-2026-0004", image="backend"))))

    def test_expired_or_overlong_acceptance(self) -> None:
        unfixed = scan(vulnerability("CVE-2026-0005", "HIGH"))
        self.assertTrue(self.judge(unfixed, accept(entry("CVE-2026-0005", recorded="2026-08-01", expires="2026-10-27"))))
        with self.assertRaises(check_image_scan.ScanError):
            self.judge(unfixed, accept(entry("CVE-2026-0005", recorded="2026-10-01", expires="2027-10-01")))
        # 기록일을 미래로 적어 실제 수용 기간을 늘리는 경우
        with self.assertRaises(check_image_scan.ScanError):
            self.judge(unfixed, accept(entry("CVE-2026-0005", recorded="2027-06-01", expires="2027-08-30")))
        with self.assertRaises(check_image_scan.ScanError):
            self.judge(unfixed, accept({**entry("CVE-2026-0005"), "reason": "ok"}))
        with self.assertRaises(check_image_scan.ScanError):
            self.judge(unfixed, accept({**entry("CVE-2026-0005"), "id": "CVE-2026-0005\n::warning::x"}))

    def test_output_cannot_inject_workflow_commands(self) -> None:
        document = scan(vulnerability("CVE-2026-0006", "CRITICAL", package="pkg\n::add-mask::x"))
        with tempfile.TemporaryDirectory() as directory:
            scan_path, accept_path = Path(directory) / "s.json", Path(directory) / "a.json"
            scan_path.write_text(json.dumps(document), encoding="utf-8")
            accept_path.write_text(json.dumps(accept()), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = check_image_scan.main(["--image", "speech", "--scan", str(scan_path), "--accept", str(accept_path),
                                              "--today", TODAY.isoformat()])
        self.assertEqual(code, 1)
        self.assertNotIn("\n::add-mask::", out.getvalue())

    def test_malformed_scan_is_error(self) -> None:
        for document in ([], {"Results": "x"}, {"Results": [{"Vulnerabilities": [{"Severity": "HIGH"}]}]}):
            with self.subTest(document=document), self.assertRaises(check_image_scan.ScanError):
                self.judge(document, accept())

    def test_repository_accept_list_is_valid(self) -> None:
        path = Path(release_manifest.ROOT) / "infra/release/image-scan-accept.json"
        for image in ("backend", "frontend", "speech"):
            check_image_scan.load_accepted(json.loads(path.read_text(encoding="utf-8")), image, TODAY)


if __name__ == "__main__":
    unittest.main()
