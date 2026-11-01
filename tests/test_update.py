"""copier update: template changes reach existing projects without losing their own edits."""

import shutil
from pathlib import Path

import pytest
from conftest import BASE_ANSWERS, TEMPLATE_ROOT, git_commit, run
from copier import run_copy, run_update

# The working tree, not a clone: tests must cover uncommitted template changes too.
IGNORE = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache")


def git(repo: Path, *args: str) -> None:
    run(
        [
            "git",
            "-c",
            "user.name=Template Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            *args,
        ],
        cwd=repo,
    )


@pytest.fixture
def template_repo(tmp_path: Path) -> Path:
    """A throwaway copy of the template, released as v1.0.0 (copier update follows tags)."""
    repo = tmp_path / "template"
    shutil.copytree(TEMPLATE_ROOT, repo, ignore=IGNORE)
    git(repo, "init", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "release 1.0.0")
    git(repo, "tag", "v1.0.0")
    return repo


def release(repo: Path, version: str) -> None:
    git(repo, "commit", "-am", f"release {version}")
    git(repo, "tag", f"v{version}")


def generate(template_repo: Path, dst: Path, **answers: object) -> Path:
    run_copy(
        str(template_repo),
        dst,
        data={**BASE_ANSWERS, **answers},
        defaults=True,
        unsafe=True,
        quiet=True,
    )
    run(["git", "add", "-A"], cwd=dst)
    result = git_commit(dst, "chore: initial commit")
    assert result.returncode == 0, result.stdout + result.stderr
    return dst


def commit_all(project: Path, message: str) -> None:
    run(["git", "add", "-A"], cwd=project)
    result = git_commit(project, message)
    assert result.returncode == 0, result.stdout + result.stderr


def assert_clean_merge(project: Path) -> None:
    # Tracked and new-but-not-ignored files: what the project would commit, not .venv/build.
    listed = run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=project)
    for name in listed.stdout.splitlines():
        path = project / name
        assert not path.name.endswith(".rej"), f"rejected hunk: {path}"
        assert "<<<<<<<" not in path.read_text(errors="ignore"), f"conflict markers in {path}"


def test_update_merges_template_change_with_local_edits(template_repo, tmp_path):
    project = generate(template_repo, tmp_path / "project", languages=["python"])

    # The project's own edits: one in a template-managed file, one in a file it owns.
    gitignore = project / ".gitignore"
    gitignore.write_text(gitignore.read_text() + "\n# Local\nscratch/\n")
    (project / "README.md").write_text("# Demo Project\n\nHand-written README.\n")
    commit_all(project, "docs: customise")

    # A template change to the same file, elsewhere in it.
    template_file = template_repo / "template/.gitignore.jinja"
    template_file.write_text("# Managed by project-template\n" + template_file.read_text())
    release(template_repo, "1.1.0")

    run_update(project, defaults=True, overwrite=True, unsafe=True, quiet=True)

    merged = gitignore.read_text()
    assert merged.startswith("# Managed by project-template")  # template change arrived
    assert "scratch/" in merged  # local edit survived the 3-way merge
    assert (project / "README.md").read_text() == "# Demo Project\n\nHand-written README.\n"
    assert "_commit: v1.1.0" in (project / ".copier-answers.yml").read_text()
    assert_clean_merge(project)


def test_update_can_add_a_language_layer(template_repo, tmp_path):
    # Changing an answer re-renders with the new answer: adding C to a Python project.
    project = generate(template_repo, tmp_path / "project", languages=["python"])
    run_update(
        project,
        data={"languages": ["python", "c"], "c_test_framework": "unity"},
        defaults=True,
        overwrite=True,
        unsafe=True,
        quiet=True,
    )
    assert (project / "CMakeLists.txt").is_file()
    assert (project / "pyproject.toml").is_file()
    assert "clang-format" in (project / ".pre-commit-config.yaml").read_text()
    assert_clean_merge(project)


def test_update_keeps_uv_lock_in_sync(template_repo, tmp_path):
    # Adding Python later must also produce a lockfile, or CI's `uv sync --locked` fails.
    project = generate(
        template_repo, tmp_path / "project", languages=["c"], c_test_framework="unity"
    )
    run_update(
        project,
        data={"languages": ["c", "python"]},
        defaults=True,
        overwrite=True,
        unsafe=True,
        quiet=True,
    )
    assert (project / "uv.lock").is_file()
    run(["uv", "lock", "--check"], cwd=project)
