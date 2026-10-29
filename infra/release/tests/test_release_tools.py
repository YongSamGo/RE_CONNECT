"""릴리스 manifest·이미지 검사 판정 시험. 저장소 루트에서 python -m unittest discover -s infra/release/tests"""

import datetime as dt
import io
import json
import re
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
# 가짜 계정 번호. manifest에는 들어가지 않고 images-env 인자로만 쓴다.
REGISTRY = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com"
IMAGES = {
    "backend": "reconnect-backend" + DIGEST,
    "frontend": "reconnect-frontend" + DIGEST,
    "speech": "reconnect-speech" + DIGEST,
}
TODAY = dt.date(2026, 10, 28)


class ReleaseManifestTest(unittest.TestCase):
    def test_build_records_versions_from_repository(self) -> None:
        manifest = release_manifest.build(release_manifest.ROOT, "v0.1.0", COMMIT, IMAGES, {})
        self.assertEqual(manifest["images"], IMAGES)
        self.assertEqual(len(manifest["migrations"]["heads"]), 1)
        prompts = (release_manifest.ROOT / "backend/app/modules/generation/prompts.py").read_text(encoding="utf-8")
        expected = re.search(r'^PROMPT_VERSION = "([^"]+)"', prompts, re.M).group(1)
        self.assertEqual(manifest["prompts"]["generation"], expected)
        self.assertEqual(set(manifest["lockfiles"]), set(release_manifest.LOCKFILES))
        for refs in manifest["base_images"].values():
            self.assertTrue(refs and all("@sha256:" in ref for ref in refs))
        self.assertNotIn("password", json.dumps(manifest).lower())
        # 공개 Release에 첨부되므로 계정 번호·레지스트리 주소가 없어야 한다.
        self.assertNotIn("dkr.ecr", json.dumps(manifest))
        self.assertNotIn("123456789012", json.dumps(manifest))

    def test_build_rejects_tags_and_unpinned_references(self) -> None:
        bad_refs = (
            IMAGES["backend"].split("@")[0] + ":latest",
            IMAGES["backend"].replace("b" * 64, "B" * 64),
            IMAGES["backend"] + "\nFRONTEND_IMAGE=evil/x" + DIGEST,
            "evil.example/x" + DIGEST + " ; rm -rf /",
            # 레지스트리 주소(계정 ID)가 섞이면 공개 manifest에 남으므로 거절한다
            REGISTRY + "/" + IMAGES["backend"],
            # 이름과 다른 저장소를 가리키면 거절한다
            "reconnect-frontend" + DIGEST,
            "reconnect-backend-x" + DIGEST,
            "reconnect-backend@sha512:" + "b" * 128,
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
        text = release_manifest.images_env(manifest, REGISTRY)
        self.assertEqual(text.splitlines()[0], "BACKEND_IMAGE=" + REGISTRY + "/" + IMAGES["backend"])
        self.assertEqual(len(text.splitlines()), 3)
        tampered = (
            {**IMAGES, "backend": "x:latest"},
            {**IMAGES, "extra": IMAGES["backend"]},
            {},
            {**IMAGES, "backend": "evil.example/" + IMAGES["backend"]},
            {**IMAGES, "backend": IMAGES["speech"]},
        )
        for images in tampered:
            with self.subTest(images=images), self.assertRaises(release_manifest.ManifestError):
                release_manifest.images_env({**manifest, "images": images}, REGISTRY)
        for schema in (1, 3, "2"):
            with self.subTest(schema=schema), self.assertRaises(release_manifest.ManifestError):
                release_manifest.images_env({**manifest, "schema": schema}, REGISTRY)

    def test_images_env_rejects_forged_registry(self) -> None:
        manifest = release_manifest.build(release_manifest.ROOT, "v0.1.0", COMMIT, IMAGES, {})
        forged = (
            "evil.example",
            "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com.evil.example",
            "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/other",
            "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com:443",
            "12345678901.dkr.ecr.ap-northeast-2.amazonaws.com",
            "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com\nFRONTEND_IMAGE=evil",
            "",
        )
        for registry in forged:
            with self.subTest(registry=registry), self.assertRaises(release_manifest.ManifestError):
                release_manifest.images_env(manifest, registry)

    def test_backend_image_includes_every_management_command(self) -> None:
        # 새 manage_*.py가 생겨도 이미지에서 빠지지 않도록 이름 나열 대신 glob으로 복사해야 한다.
        dockerfile = (release_manifest.ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
        copies = [line.split()[1:-1] for line in dockerfile.splitlines() if line.startswith("COPY ") and "--from" not in line]
        self.assertTrue(any("manage_*.py" in sources for sources in copies))
        self.assertTrue(list((release_manifest.ROOT / "backend").glob("manage_*.py")))

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


def migration(root: Path, revision: str, down: str | None, safe: str | None = None) -> None:
    lines = [f"revision = {revision!r}", f"down_revision = {down!r}"]
    if safe is not None:
        lines.append(f"rollback_safe = {safe}")
    (root / f"{revision}.py").write_text("\n".join(lines) + "\n", encoding="utf-8")


def release(tag: str, heads: list[str], models: str = "m1", compose: str = "c1") -> dict[str, object]:
    return {
        "schema": release_manifest.SCHEMA,
        "tag": tag,
        "commit": COMMIT,
        "images": IMAGES,
        "models": {"backend/tools/ollama-manifest.json": models},
        "compose": {"infra/compose.prod.yaml": compose},
        "prompts": {"generation": "g1"},
        "migrations": {"heads": heads},
    }


class RollbackCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        migration(self.root, "a", None)
        migration(self.root, "b", "a")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def check(self, current: object, target: object) -> dict[str, object]:
        return release_manifest.rollback_check(current, target, self.root)

    def test_same_schema_allows_image_rollback_and_reports_model_change(self) -> None:
        result = self.check(release("v0.2.0", ["b"], models="m2"), release("v0.1.0", ["b"]))
        self.assertEqual(result["verdict"], "images_only")
        self.assertEqual(result["migrations_after_target"], [])
        self.assertEqual(result["models_changed"], ["backend/tools/ollama-manifest.json"])
        self.assertEqual(result["compose_changed"], [])

    def test_only_reviewed_additive_migrations_keep_image_rollback(self) -> None:
        migration(self.root, "c", "b", "True")
        migration(self.root, "d", "c", "True")
        result = self.check(release("v0.2.0", ["d"]), release("v0.1.0", ["b"]))
        self.assertEqual(result["verdict"], "schema_compatible")
        self.assertEqual(result["migrations_after_target"], ["c", "d"])

    def test_undeclared_or_non_boolean_marker_requires_restore(self) -> None:
        migration(self.root, "c", "b", "True")
        migration(self.root, "d", "c")
        migration(self.root, "e", "d", '"True"')
        migration(self.root, "f", "e", "1")
        result = self.check(release("v0.2.0", ["f"]), release("v0.1.0", ["b"]))
        self.assertEqual(result["verdict"], "restore_required")
        self.assertEqual(result["not_rollback_safe"], ["d", "e", "f"])

    def test_merge_revision_counts_both_branches(self) -> None:
        migration(self.root, "c", "a", "True")
        migration(self.root, "d", ("b", "c"))
        result = self.check(release("v0.2.0", ["d"]), release("v0.1.0", ["b"]))
        self.assertEqual(result["migrations_after_target"], ["c", "d"])
        self.assertEqual(result["not_rollback_safe"], ["d"])

    def test_refuses_when_not_a_rollback(self) -> None:
        migration(self.root, "c", "a")
        cases = (
            # 체크아웃이 current 릴리스가 아니다
            (release("v0.2.0", ["b"]), release("v0.1.0", ["a"])),
            # target이 다른 갈래다
            (release("v0.2.0", ["b", "c"]), release("v0.1.0", ["x"])),
            # 같은 릴리스
            (release("v0.2.0", ["b", "c"]), release("v0.2.0", ["b"])),
        )
        for current, target in cases:
            with self.subTest(current=current["migrations"], target=target["migrations"]):
                with self.assertRaises(release_manifest.ManifestError):
                    self.check(current, target)

    def test_newer_target_with_same_schema_is_refused(self) -> None:
        # 스키마가 같아도 더 새 릴리스로 가는 것은 되돌리기가 아니다 (images_only로 통과하면 안 된다)
        for current, target in (("v0.2.0", "v0.3.0"), ("v0.9.0", "v0.10.0"), ("v1.0.0-rc.1", "v1.0.0"),
                                ("v1.0.0-rc.1", "v1.0.0-rc.2"), ("v0.2.0", "v0.2.0")):
            with self.subTest(current=current, target=target), self.assertRaises(release_manifest.ManifestError):
                self.check(release(current, ["b"]), release(target, ["b"]))
        for current, target in (("v0.10.0", "v0.9.0"), ("v1.0.0", "v1.0.0-rc.3"), ("v1.0.0-rc.2", "v1.0.0-rc.1"),
                                ("v2.0.0", "v1.99.99")):
            with self.subTest(current=current, target=target):
                self.assertEqual(self.check(release(current, ["b"]), release(target, ["b"]))["verdict"], "images_only")

    def test_target_newer_than_current_is_refused(self) -> None:
        migration(self.root, "c", "b")
        with self.assertRaises(release_manifest.ManifestError):
            self.check(release("v0.1.0", ["c"]), release("v0.2.0", ["d"]))

    def test_tampered_manifests_are_refused(self) -> None:
        good = release("v0.1.0", ["b"])
        tampered = (
            {**good, "schema": 1},
            {**good, "tag": "main"},
            {**good, "migrations": {"heads": "b"}},
            {**good, "migrations": {"heads": []}},
            {**good, "migrations": {"heads": ["b", "b"]}},
            {**good, "migrations": None},
            {**good, "images": {**IMAGES, "backend": "evil.example/x" + DIGEST}},
            {**good, "models": ["x"]},
            {**good, "compose": {"infra/compose.prod.yaml": 1}},
            [],
        )
        for manifest in tampered:
            with self.subTest(manifest=manifest), self.assertRaises(release_manifest.ManifestError):
                self.check(release("v0.2.0", ["b"]), manifest)
            with self.subTest(current=manifest), self.assertRaises(release_manifest.ManifestError):
                self.check(manifest, release("v0.0.1", ["a"]))

    def test_duplicate_revision_is_refused(self) -> None:
        (self.root / "b_copy.py").write_text('revision = "b"\ndown_revision = "a"\n', encoding="utf-8")
        with self.assertRaises(release_manifest.ManifestError):
            self.check(release("v0.2.0", ["b"]), release("v0.1.0", ["a"]))

    def test_cli_exit_codes(self) -> None:
        migration(self.root, "c", "b")
        paths = {}
        for name, manifest in (("now", release("v0.2.0", ["c"])), ("same", release("v0.1.1", ["c"])),
                               ("old", release("v0.1.0", ["b"]))):
            paths[name] = self.root.parent / f"{self.root.name}-{name}.json"
            paths[name].write_text(json.dumps(manifest), encoding="utf-8")
            self.addCleanup(paths[name].unlink)
        for target, code, verdict in (("same", 0, "images_only"), ("old", 2, "restore_required")):
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                result = release_manifest.main(["rollback-check", "--current", str(paths["now"]), "--target",
                                                str(paths[target]), "--versions", str(self.root)])
            self.assertEqual(result, code)
            self.assertEqual(json.loads(out.getvalue())["verdict"], verdict)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(release_manifest.main(["rollback-check", "--current", str(paths["old"]), "--target",
                                                    str(paths["now"]), "--versions", str(self.root)]), 1)

    def test_repository_migrations_without_marker_require_restore(self) -> None:
        versions = release_manifest.ROOT / "backend/migrations/versions"
        head = release_manifest.migration_heads(versions)
        graph, _ = release_manifest.migration_graph(versions)
        parent = list(graph[head[0]])
        result = release_manifest.rollback_check(release("v0.2.0", head), release("v0.1.0", parent), versions)
        self.assertEqual(result["migrations_after_target"], head)
        self.assertEqual(result["verdict"], "restore_required")

    def test_migration_template_declares_marker(self) -> None:
        template = (release_manifest.ROOT / "backend/migrations/script.py.mako").read_text(encoding="utf-8")
        self.assertIn("\nrollback_safe = False\n", template)


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
