"""release: optional release-please setup, with every version-bearing file kept in sync."""

import json

import pytest
import yaml
from conftest import assert_ok, run

RELEASE_FILES = [
    ".github/workflows/release.yml",
    "release-please-config.json",
    ".release-please-manifest.json",
]
BOTH = {"languages": ["python", "c"], "c_test_framework": "unity"}


def extra_files(project) -> list:
    config = json.loads((project / "release-please-config.json").read_text())
    return config["packages"]["."]["extra-files"]


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"profile": "project", "release": True}, True),
        ({"profile": "project", "release": False}, False),
        ({"profile": "project"}, False),  # opt-in: needs the App and repo settings first
        ({"profile": "learning"}, False),  # never asked for learning, so stays off
    ],
)
def test_release_files_only_when_enabled(render, answers, expected):
    project = render(**answers)
    for name in RELEASE_FILES:
        assert (project / name).is_file() == expected, name


@pytest.mark.parametrize(
    ("languages", "paths"),
    [
        ([], []),
        (["python"], ["pyproject.toml", "uv.lock"]),
        (["c"], ["CMakeLists.txt"]),
        (["python", "c"], ["pyproject.toml", "uv.lock", "CMakeLists.txt"]),
    ],
)
def test_extra_files_match_languages(render, languages, paths):
    framework = {"c_test_framework": "unity"} if "c" in languages else {}
    project = render(profile="project", release=True, languages=languages, **framework)
    listed = [e if isinstance(e, str) else e["path"] for e in extra_files(project)]
    assert listed == paths
    for path in listed:
        assert (project / path).is_file(), f"extra-files names missing {path}"


def test_uv_lock_entry_targets_the_project_package(render):
    # release-please's TOML parser wraps values as {value: ...}, hence `@.name.value`.
    project = render(profile="project", release=True, languages=["python"])
    (lock,) = [e for e in extra_files(project) if e["path"] == "uv.lock"]
    assert lock["jsonpath"] == "$.package[?(@.name.value=='demo-project')].version"
    assert 'name = "demo-project"' in (project / "uv.lock").read_text()


def test_cmake_version_line_is_marked(render):
    project = render(profile="project", release=True, languages=["c"], c_test_framework="unity")
    (line,) = [
        line
        for line in (project / "CMakeLists.txt").read_text().splitlines()
        if "x-release-please-version" in line
    ]
    assert "VERSION 0.1.0" in line


def test_no_marker_without_release(render):
    project = render(profile="project", languages=["c"], c_test_framework="unity")
    assert "x-release-please-version" not in (project / "CMakeLists.txt").read_text()


def test_release_workflow_keeps_github_expressions(render):
    # The workflow is copied verbatim: Jinja must not eat GitHub's ${{ }} expressions.
    project = render(profile="project", release=True)
    workflow = yaml.safe_load((project / ".github/workflows/release.yml").read_text())
    steps = workflow["jobs"]["release-please"]["steps"]
    assert steps[0]["with"]["client-id"] == "${{ vars.RELEASE_APP_CLIENT_ID }}"


def test_release_render_is_green(render):
    project = render(profile="project", release=True, **BOTH)
    run(["git", "add", "-A"], cwd=project)
    assert_ok(["pre-commit", "run", "--all-files"], project)
