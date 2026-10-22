"""Files and behaviour every rendered project must have, whatever its languages."""

from datetime import date

import pytest
import yaml
from conftest import git_commit, run

PROFILES = ["project", "learning"]
PROJECT_ONLY = [
    "CONTRIBUTING.md",
    ".github/pull_request_template.md",
    ".github/dependabot.yml",
]


@pytest.mark.parametrize("profile", PROFILES)
def test_common_files(render, profile):
    project = render(profile=profile)
    for name in [
        ".copier-answers.yml",
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        ".pre-commit-config.yaml",
        ".github/workflows/ci.yml",
        "README.md",
        "CLAUDE.md",
        "LICENSE",
    ]:
        assert (project / name).is_file(), f"missing {name}"

    for name in PROJECT_ONLY:
        assert (project / name).is_file() == (profile == "project"), name


def test_answers_file_records_template(render):
    answers = yaml.safe_load((render() / ".copier-answers.yml").read_text())
    assert answers["_src_path"]
    assert answers["profile"] == "project"


def test_slug_derived_from_name(render):
    answers = yaml.safe_load(
        (render(project_name="My Cool_Tool 2") / ".copier-answers.yml").read_text()
    )
    assert answers["project_slug"] == "my-cool-tool-2"


def test_mit_license_filled_in(render):
    text = (render(license="mit") / "LICENSE").read_text()
    assert text.startswith("MIT License")
    assert f"Copyright (c) {date.today().year} 7echkilla" in text
    assert "[year]" not in text and "[fullname]" not in text


@pytest.mark.parametrize("license_key", ["apache-2.0", "gpl-3.0", "agpl-3.0"])
def test_other_licenses(render, license_key):
    project = render(license=license_key)
    assert (project / "LICENSE").stat().st_size > 1000
    assert not (project / "COPYING").exists()


@pytest.mark.parametrize("license_key", ["mit", "apache-2.0", "gpl-3.0", "lgpl-3.0", "agpl-3.0"])
def test_license_files_end_with_single_newline(render, license_key):
    # end-of-file-fixer would rewrite them on the first commit otherwise.
    project = render(license=license_key)
    for name in ["LICENSE", "COPYING"]:
        if (path := project / name).exists():
            text = path.read_text()
            assert text.endswith("\n") and not text.endswith("\n\n"), name


def test_lgpl_ships_gpl_too(render):
    project = render(license="lgpl-3.0")
    assert "LESSER GENERAL PUBLIC LICENSE" in (project / "LICENSE").read_text()
    assert "GNU GENERAL PUBLIC LICENSE" in (project / "COPYING").read_text()


def test_no_license(render):
    project = render(license="none")
    assert not (project / "LICENSE").exists()
    assert "## License" not in (project / "README.md").read_text()


def test_ci_workflow_is_valid_yaml_without_jinja_leftovers(render):
    text = (render() / ".github/workflows/ci.yml").read_text()
    assert "{%" not in text
    assert "${{ github.workflow }}" in text  # Actions expressions must survive rendering
    yaml.safe_load(text)


# --- Hooks: these define what .pre-commit-config.yaml.jinja must do -------------


@pytest.mark.parametrize("profile", PROFILES)
def test_hooks_installed_and_pass_on_fresh_render(render, profile):
    project = render(profile=profile)
    hooks = project / ".git" / "hooks"
    assert (hooks / "pre-commit").is_file(), "pre-commit hook not installed"
    assert (hooks / "commit-msg").is_file(), "commit-msg hook not installed"

    run(["git", "add", "-A"], cwd=project)
    result = run(["pre-commit", "run", "--all-files"], cwd=project, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_commit_message_must_be_conventional(render):
    project = render()
    run(["git", "add", "-A"], cwd=project)
    assert git_commit(project, "updated some stuff").returncode != 0
    assert git_commit(project, "chore: initial commit").returncode == 0


def test_private_key_is_blocked(render):
    project = render()
    run(["git", "add", "-A"], cwd=project)
    assert git_commit(project, "chore: initial commit").returncode == 0

    # Assembled at runtime so this source file doesn't itself trip detect-private-key.
    marker = "OPENSSH " + "PRIVATE KEY"
    (project / "id_test").write_text(
        f"-----BEGIN {marker}-----\nnot-a-real-key\n-----END {marker}-----\n"
    )
    run(["git", "add", "id_test"], cwd=project)
    assert git_commit(project, "feat: add key").returncode != 0


def test_whitespace_is_fixed(render):
    project = render()
    run(["git", "add", "-A"], cwd=project)
    assert git_commit(project, "chore: initial commit").returncode == 0

    (project / "notes.txt").write_text("trailing   \nno newline at end")
    run(["git", "add", "notes.txt"], cwd=project)
    # Fixer hooks rewrite the file and fail the commit so you can review the change...
    assert git_commit(project, "docs: add notes").returncode != 0
    assert (project / "notes.txt").read_text() == "trailing\nno newline at end\n"
    # ...and the re-staged commit then goes through.
    run(["git", "add", "notes.txt"], cwd=project)
    assert git_commit(project, "docs: add notes").returncode == 0
