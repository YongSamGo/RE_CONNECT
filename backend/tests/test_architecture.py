"""모듈 의존 방향 검사 (app/modules/__init__.py, Plan/03 §2).

허용: router → service → repository/Adapter Protocol. 구체 구현은 app/main.py에서만 고른다.
"""

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def module_name(path: Path) -> str:
    return ".".join(path.relative_to(APP_DIR.parent).with_suffix("").parts)


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
