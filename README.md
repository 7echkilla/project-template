# project-template

A [Copier](https://copier.readthedocs.io/) template that sets up a new repository with my standards built in: formatting, linting, Conventional Commits, CI, and optional SemVer releases.

**Status:** in development. Not ready for use until `v0.1.0`.

## Usage

```bash
# New project
copier copy --trust gh:7echkilla/project-template my-project

# Pull template changes into an existing project
copier update --trust
```

`--trust` is needed because the template runs setup tasks (`git init`, `pre-commit install`) after rendering.

## License

[MIT](LICENSE)
