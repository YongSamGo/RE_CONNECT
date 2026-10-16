"""모듈 의존 방향 검사 (app/modules/__init__.py, Plan/03 §2).

허용: router → service → repository/Adapter Protocol. 구체 구현은 app/main.py에서만 고른다.
"""

import ast
import importlib.util
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(APP_DIR.parent).with_suffix("").parts)


def package_name(path: Path) -> str:
    name = module_name(path)
    return name if path.name == "__init__.py" else name.rpartition(".")[0]


def imported_modules(path: Path, package: str | None = None) -> set[str]:
    """파일이 import하는 모듈 이름. 상대 import는 파일 위치 기준의 절대 이름으로 푼다."""
    package = package if package is not None else package_name(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
            elif node.module:
                base = node.module
            else:
                continue
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def python_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


def test_app_directory_has_python_files() -> None:
    # 경로가 바뀌어 아래 검사가 빈 목록으로 통과하는 일을 막는다.
    assert python_files(APP_DIR / "modules")
    assert python_files(APP_DIR / "core")
    assert python_files(APP_DIR / "adapters")


def test_routers_do_not_import_repositories_or_adapters() -> None:
    for path in (APP_DIR / "modules").rglob("router.py"):
        for name in imported_modules(path):
            assert not name.startswith("app.adapters"), f"{module_name(path)} → {name}"
            assert ".repository" not in name, f"{module_name(path)} → {name}"


def test_modules_do_not_use_other_modules_repositories() -> None:
    for path in python_files(APP_DIR / "modules"):
        parts = module_name(path).split(".")
        if len(parts) < 3:
            continue
        own_module = parts[2]
        for name in imported_modules(path):
            name_parts = name.split(".")
            if name.startswith("app.modules.") and len(name_parts) > 3 and name_parts[3] == "repository":
                assert name_parts[2] == own_module, f"{module_name(path)} → {name}"


def test_core_and_adapters_do_not_depend_on_modules() -> None:
    for directory in (APP_DIR / "core", APP_DIR / "adapters"):
        for path in python_files(directory):
            for name in imported_modules(path):
                assert not name.startswith("app.modules"), f"{module_name(path)} → {name}"
                assert not name.startswith("app.main"), f"{module_name(path)} → {name}"


def test_only_main_assembles_the_app() -> None:
    for path in python_files(APP_DIR):
        if path.name == "main.py" and path.parent == APP_DIR:
            continue
        assert "app.main" not in imported_modules(path), module_name(path)


@pytest.mark.parametrize(
    "source",
    [
        "from .repository import JourneyRepository",
        "from . import repository",
        "from ...adapters.llm import LLMAdapter",
        "from ... import adapters",
    ],
)
def test_relative_imports_are_resolved_and_caught(tmp_path: Path, source: str) -> None:
    router = tmp_path / "router.py"
    router.write_text(source, encoding="utf-8")

    names = imported_modules(router, package="app.modules.journey")

    assert any(name.startswith("app.adapters") or ".repository" in name for name in names), names
