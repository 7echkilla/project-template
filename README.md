# project-template

A [Copier](https://copier.readthedocs.io/) template that sets up a new repository with my standards built in: formatting, linting, Conventional Commits, CI, and optional SemVer releases.

**Status:** active. Released versions are listed in [CHANGELOG.md](CHANGELOG.md).

## Usage

```bash
# New project
copier copy --trust gh:7echkilla/project-template my-project

# Pull template changes into an existing project
copier update --trust
```

`--trust` is needed because the template runs setup tasks (`git init`, `uv lock`, `pre-commit install`) after rendering.

Copier uses the newest release tag, not the newest commit on `main`. Each project records the version it was generated from in `.copier-answers.yml`, and `copier update` moves it to the newest tag.

## Developing the template

```bash
uv sync              # dev tools: copier, pre-commit, pytest, ninja
pre-commit install
uv run pytest        # renders every language/profile combination and checks each one
```

Changes go through a PR to `main` with a Conventional Commit title. release-please keeps a release PR open, and merging it tags the next version.

## License

[MIT](LICENSE)
