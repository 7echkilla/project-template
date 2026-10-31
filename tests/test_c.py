"""The C layer: rendered only when selected, builds and tests, and enforces its standards."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import assert_ok, git_commit, run

C = {"languages": ["c"], "c_test_framework": "unity"}


def has_criterion() -> bool:
    if shutil.which("pkg-config") is None:
        return False
    return subprocess.run(["pkg-config", "--exists", "criterion"]).returncode == 0


# Criterion and clang-tidy are system packages that local machines may lack. Template CI
# installs both, so there (CI is set) a missing tool must fail loudly, never skip silently.
IN_CI = bool(os.environ.get("CI"))

CRITERION = pytest.param(
    "criterion",
    marks=pytest.mark.skipif(
        not has_criterion() and not IN_CI, reason="libcriterion-dev not installed"
    ),
)


# --- Structure (plumbing) -------------------------------------------------------


def test_no_c_files_without_c(render):
    project = render(languages=["python"])
    for name in [
        "CMakeLists.txt",
        "CMakePresets.json",
        ".clang-format",
        ".clang-tidy",
        "include",
        "src/main.c",
        "tests/CMakeLists.txt",
    ]:
        assert not (project / name).exists(), f"unexpected {name}"
    ci = yaml.safe_load((project / ".github/workflows/ci.yml").read_text())
    assert "c" not in ci["jobs"]


def test_c_files(render):
    project = render(**C)
    for name in [
        "CMakeLists.txt",
        "CMakePresets.json",
        ".clang-format",
        ".clang-tidy",
        "include/demo_project/demo_project.h",
        "src/demo_project.c",
        "src/main.c",
        "tests/CMakeLists.txt",
        "tests/test_demo_project.c",
    ]:
        assert (project / name).is_file(), f"missing {name}"
    ci = yaml.safe_load((project / ".github/workflows/ci.yml").read_text())
    assert "c" in ci["jobs"]


@pytest.mark.parametrize(
    ("framework", "test_file"),
    [
        ("unity", "test_demo_project.c"),
        ("googletest", "test_demo_project.cpp"),
        ("criterion", "test_demo_project.c"),
    ],
)
def test_test_file_per_framework(render, framework, test_file):
    project = render(languages=["c"], c_test_framework=framework)
    assert (project / "tests" / test_file).is_file()


def test_no_test_framework(render):
    project = render(languages=["c"], c_test_framework="none")
    tests = project / "tests"
    assert not tests.exists() or not any(tests.iterdir())


# --- Behaviour: these define what CMakeLists.txt and the C sources must do -------
#
# The library's public API, used by every starter test:
#     include/<package_name>/<package_name>.h  declares  int <package_name>_add(int a, int b);


def workflow(project: Path, preset: str = "dev") -> None:
    assert_ok(["cmake", "--workflow", "--preset", preset], project)


def compile_command(project: Path, source: str) -> str:
    entries = json.loads((project / "build/dev/compile_commands.json").read_text())
    for entry in entries:
        if entry["file"].endswith(source):
            return entry["command"]
    raise AssertionError(f"{source} is not compiled by any target")


@pytest.mark.parametrize("framework", ["unity", "googletest", CRITERION, "none"])
def test_c_render_is_green(render, framework):
    project = render(languages=["c"], c_test_framework=framework)
    workflow(project)
    run(["git", "add", "-A"], cwd=project)
    assert_ok(["pre-commit", "run", "--all-files"], project)


@pytest.mark.parametrize("framework", ["unity", "googletest"])
def test_tests_are_registered_with_ctest(render, framework):
    # A build with zero registered tests would also "pass": make sure the tests really run.
    project = render(languages=["c"], c_test_framework=framework)
    workflow(project)
    listing = run(["ctest", "--preset", "dev", "--show-only"], cwd=project).stdout
    assert "Total Tests: 0" not in listing, listing


def test_app_builds_and_runs(render):
    project = render(**C)
    workflow(project)
    result = run([str(project / "build/dev/demo-project")], cwd=project, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "the app should print something"


@pytest.mark.parametrize("standard", ["11", "17"])
def test_c_standard_applied_without_extensions(render, standard):
    project = render(c_standard=standard, **C)
    workflow(project)
    command = compile_command(project, "src/demo_project.c")
    assert f"-std=c{standard}" in command, command  # not -std=gnu17: portable ISO C only


def test_warnings_enabled(render):
    project = render(**C)
    workflow(project)
    for source in ["src/demo_project.c", "src/main.c"]:
        command = compile_command(project, source)
        for flag in ["-Wall", "-Wextra", "-Wpedantic"]:
            assert flag in command, f"{flag} missing for {source}"


def test_ci_preset_treats_warnings_as_errors(render):
    project = render(**C)
    with (project / "src/demo_project.c").open("a") as source:
        source.write("\nstatic int unused_helper(void) { return 0; }\n")
    workflow(project, "dev")  # a warning locally...
    result = run(["cmake", "--workflow", "--preset", "ci"], cwd=project, check=False)
    assert result.returncode != 0  # ...an error in CI
    assert "unused" in result.stdout + result.stderr


def test_asan_preset(render):
    workflow(render(**C), "asan")


@pytest.mark.skipif(
    shutil.which("clang-tidy") is None and not IN_CI, reason="clang-tidy not installed"
)
def test_lint_preset(render):
    workflow(render(**C), "lint")


def test_clang_format_blocks_unformatted_code(render):
    project = render(**C)
    run(["git", "add", "-A"], cwd=project)
    initial = git_commit(project, "chore: initial commit")
    assert initial.returncode == 0, initial.stdout + initial.stderr
    with (project / "src/demo_project.c").open("a") as source:
        source.write("int   ugly( void ){return 0;}\n")
    run(["git", "add", "-A"], cwd=project)
    result = git_commit(project, "feat: add ugly function")
    assert result.returncode != 0
    assert "clang-format" in result.stdout + result.stderr


def test_polyglot_python_and_c(render):
    project = render(languages=["python", "c"], c_test_framework="unity")
    assert_ok(["uv", "sync", "--locked"], project)
    assert_ok(["uv", "run", "pytest"], project)
    assert_ok(["uv", "run", "pyright"], project)
    workflow(project)
    run(["git", "add", "-A"], cwd=project)
    assert_ok(["pre-commit", "run", "--all-files"], project)
