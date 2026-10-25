"""Helpers for rendering the template into throwaway projects."""

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from copier import run_copy

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent

# Minimal answers every render needs; tests override per case.
BASE_ANSWERS = {
    "project_name": "Demo Project",
    "description": "A throwaway project rendered by the template tests.",
    "license": "mit",
}


# `uv run pytest` exports the template repo's VIRTUAL_ENV; rendered projects must use their own.
CHILD_ENV = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True, env=CHILD_ENV)


def assert_ok(cmd: list[str], cwd: Path) -> None:
    """Run a command and fail the test with its full output if it doesn't succeed."""
    result = run(cmd, cwd, check=False)
    assert result.returncode == 0, f"$ {' '.join(cmd)}\n{result.stdout}{result.stderr}"


def git_commit(project: Path, message: str) -> subprocess.CompletedProcess[str]:
    # The rendered repo has no remote, so the global "identity from remote" rule would
    # refuse to commit; give it a throwaway identity and skip signing.
    return run(
        [
            "git",
            "-c",
            "user.name=Template Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            message,
        ],
        cwd=project,
        check=False,
    )


@pytest.fixture
def render(tmp_path: Path) -> Callable[..., Path]:
    def _render(**answers: object) -> Path:
        dst = tmp_path / "project"
        run_copy(
            str(TEMPLATE_ROOT),
            dst,
            data={**BASE_ANSWERS, **answers},
            defaults=True,
            unsafe=True,  # allow _tasks (git init, pre-commit install)
            vcs_ref="HEAD",  # include uncommitted template changes while developing
            quiet=True,
        )
        return dst

    return _render
