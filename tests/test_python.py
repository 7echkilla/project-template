"""The python layer: rendered only when selected, and green out of the box."""

import tomllib
from pathlib import Path

import pytest
import yaml
from conftest import assert_ok, git_commit, run

PYTHON = {"languages": ["python"]}


def has_files(path: Path) -> bool:
    return path.exists() and any(p.is_file() for p in path.rglob("*"))


# --- Structure (plumbing) -------------------------------------------------------


def test_no_python_files_without_python(render):
    project = render(languages=[])
    assert not (project / "pyproject.toml").exists()
    assert not (project / "uv.lock").exists()
    assert not has_files(project / "src")
    assert not has_files(project / "tests")
    ci = yaml.safe_load((project / ".github/workflows/ci.yml").read_text())
    assert "python" not in ci["jobs"]


def test_python_files(render):
    project = render(**PYTHON)
    for name in [
        "pyproject.toml",
        "uv.lock",
        "src/demo_project/__init__.py",
        "tests/test_demo_project.py",
    ]:
        assert (project / name).is_file(), f"missing {name}"
    ci = yaml.safe_load((project / ".github/workflows/ci.yml").read_text())
    assert "python" in ci["jobs"]


def test_package_name_derived_from_slug(render):
    project = render(project_name="My Tool", **PYTHON)
    assert (project / "src/my_tool/__init__.py").is_file()
    assert (project / "tests/test_my_tool.py").is_file()


def test_dependabot_tracks_uv(render):
    project = render(profile="project", **PYTHON)
    config = yaml.safe_load((project / ".github/dependabot.yml").read_text())
    assert "uv" in [u["package-ecosystem"] for u in config["updates"]]


# --- pyproject.toml: these define what pyproject.toml.jinja must contain --------


def load_pyproject(project: Path) -> dict:
    return tomllib.loads((project / "pyproject.toml").read_text())


def test_pyproject_metadata(render):
    data = load_pyproject(render(python_version="3.13", **PYTHON))
    meta = data["project"]
    assert meta["name"] == "demo-project"
    assert meta["description"] == "A throwaway project rendered by the template tests."
    assert meta["requires-python"] == ">=3.13"
    assert data["build-system"]["build-backend"] == "uv_build"


@pytest.mark.parametrize(
    ("license_key", "spdx"),
    [
        ("mit", "MIT"),
        ("apache-2.0", "Apache-2.0"),
        ("gpl-3.0", "GPL-3.0-or-later"),
        ("agpl-3.0", "AGPL-3.0-or-later"),
    ],
)
def test_pyproject_license_is_spdx(render, license_key, spdx):
    # PEP 639: `license` is an SPDX expression, plus the files that hold the text.
    meta = load_pyproject(render(license=license_key, **PYTHON))["project"]
    assert meta["license"] == spdx
    assert meta["license-files"] == ["LICENSE"]


def test_pyproject_no_license(render):
    meta = load_pyproject(render(license="none", **PYTHON))["project"]
    assert "license" not in meta
    assert "license-files" not in meta


def test_pyproject_dev_tools_and_config(render):
    data = load_pyproject(render(**PYTHON))
    dev = " ".join(data["dependency-groups"]["dev"])
    for tool in ["pytest", "pyright", "ruff"]:
        assert tool in dev, f"{tool} missing from [dependency-groups] dev"
    assert "ruff" in data["tool"]
    assert "pyright" in data["tool"]
    assert "ini_options" in data["tool"]["pytest"]


# --- Behaviour: a fresh Python project works and its hooks bite ------------------


@pytest.mark.parametrize("profile", ["project", "learning"])
def test_python_render_is_green(render, profile):
    project = render(profile=profile, **PYTHON)
    assert_ok(["uv", "sync", "--locked"], project)
    assert_ok(["uv", "run", "pytest"], project)
    assert_ok(["uv", "run", "pyright"], project)
    run(["git", "add", "-A"], cwd=project)
    assert_ok(["pre-commit", "run", "--all-files"], project)


def commit_initial(project: Path) -> None:
    run(["git", "add", "-A"], cwd=project)
    result = git_commit(project, "chore: initial commit")
    assert result.returncode == 0, result.stdout + result.stderr


def test_ruff_blocks_lint_errors(render):
    project = render(**PYTHON)
    commit_initial(project)
    # F821 (undefined name) can't be auto-fixed, so the commit must be refused.
    (project / "src/demo_project/broken.py").write_text("print(undefined_name)\n")
    run(["git", "add", "-A"], cwd=project)
    result = git_commit(project, "feat: add broken module")
    assert result.returncode != 0
    assert "F821" in result.stdout + result.stderr


def test_pyright_blocks_type_errors(render):
    project = render(**PYTHON)
    commit_initial(project)
    # Lint-clean but wrongly typed: only the type checker can catch this.
    (project / "src/demo_project/typed.py").write_text('count: int = "three"\n')
    run(["git", "add", "-A"], cwd=project)
    result = git_commit(project, "feat: add typed module")
    assert result.returncode != 0
    assert "pyright" in (result.stdout + result.stderr).lower()


def test_pyproject_lgpl_lists_both_license_files(render):
    # LGPL-3.0 is a set of additional permissions on top of GPL-3.0, so both texts ship.
    meta = load_pyproject(render(license="lgpl-3.0", **PYTHON))["project"]
    assert meta["license"] == "LGPL-3.0-or-later"
    assert meta["license-files"] == ["LICENSE", "COPYING"]
