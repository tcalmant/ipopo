# How to contribute

All contributions to iPOPO are always welcome.

## Issues & Feedback

Issues must be described on the [GitHub repository](https://github.com/tcalmant/ipopo/issues).

Feedback is always greatly appreciated and should be given on the
[ipopo-users](https://groups.google.com/g/ipopo-users) mailing list.

New features can be requested either as an *Enhancement* issue or
discussed on the users mailing list.

## Code contribution

In order to contribute code to iPOPO, you must fork the project then use
[GitHub Pull Requests](https://github.com/tcalmant/ipopo/pulls). Your
code will be reviewed, tested and inserted into the `v3` branch, which is the
current development line.

Your code style must follow some rules, described in the following section.

If you don't write documentation or tests, I'll write some of them; but
contributing both of them will increase the changes of your pull request
to be accepted.

Note that your contributions must be released under the project's license, which
is the [Apache Software License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

## Code Style

Overall, try to respect [PEP-8](https://peps.python.org/pep-0008/).

If you use PyCharm or VS Code, most of the rules described here are
already checked.

An [EditorConfig](https://editorconfig.org/) is available in the repository:
you should make sure your IDE loads it, either natively or using a plugin
(*e.g.* [EditorConfig for VS Code](https://marketplace.visualstudio.com/items?itemName=EditorConfig.EditorConfig)).

[ruff](https://docs.astral.sh/ruff/) and [ty](https://docs.astral.sh/ty/) are
part of the development dependencies, so `uv sync` installs them. The
continuous integration rejects a pull request that doesn't pass all three of:

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check pelix tests
```

### General

- Your code must be compatible with Python 3.10+.
- Use type hints wherever possible
- Prefer using typed service specifications instead of named ones in Pelix and iPOPO
- Use `logging` instead of printing out debug traces.
- Use list, set and dictionary comprehension when possible.
- Remove unused imports.
- Imports must be after module documentation and before anything else.
- All modules must have a `__version_info__` tuple and a matching `__version__` string.

### Formatting

- Rule of thumb: use [ruff](https://docs.astral.sh/ruff/) to format your files, with `ruff format`. It is configured in `pyproject.toml`, so it doesn't need any argument.
- Avoid inline comments; use 2 spaces when using them (mainly for type hinting)
- Break long lines after **110** characters. Exception for URLs.
- Delete trailing whitespace.
- Don't include spaces after `(`, `[`, `{` or before `}`, `]`, `)`.
- Don't misspell in method names.
- Don't vertically align tokens on consecutive lines.
- Use 4 spaces indentation (no tabs).
- Use an empty line between methods.
- Use 2 empty lines before class definitions.
- Use spaces around operators.
- Use spaces after commas and colons.
- Use Unix-style line endings (`\n`).
- Use 3 double-quotes (`"""`) for documentation

### Naming

- Use `CamelCase` for class names.
- Use `SNAKE_UPPERCASE` for constants.
- Use `snake_case` for method names.
- `CamelCase` is allowed for decorator methods.
- First argument of:
  - instance methods must be `self`
  - class methods must be `cls`

### Organization

Documentation about a new feature should be added to a new file in
`docs/refcards`.
Documentation is compiled with [Sphinx](https://www.sphinx-doc.org/) and
supports both reStructuredText and Markdown (with
[MyST](https://myst-parser.readthedocs.io/)).

New features implementations can be added either to an existing or to a new
`pelix` subpackage. You should not add new modules to the root `pelix`
package.

Tests should be added to either an existing or a new sub-folder of `tests`.
Unit tests are executed using `pytest` and based on `unittest`.

You can also provide new samples in the `samples` folder. They must come
as a `run_XXX.py` entry-point script and an `XXX` package containing all
the sample bundles.

## Releasing

Releases are made by the maintainer. The process is written down here so that it
is reproducible, not because it is open to contributors.

A release is prepared on a dedicated branch (`release-X.Y.Z`), merged into `v3`
through a pull request, then published by pushing a signed tag.

1. **Bump the version.** It is declared in `pyproject.toml`, and, in every module
   of `pelix` and `tests`, both as a `__version_info__` tuple and as a
   `:version:` field of the module docstring. All of them must agree:

   ```bash
   python .github/scripts/check_version.py
   ```

2. **Set the release date** in `docs/changelog.md`, replacing `Unreleased` in the
   admonition of the section of the version being released. That section is the
   source of the GitHub release notes, so it must describe the release
   completely. Security fixes go in a `### Security` subsection.

3. **Check the branch locally**, as the continuous integration does:

   ```bash
   uv sync --all-extras --locked
   uv run ruff check . && uv run ruff format --check .
   uv run ty check pelix tests
   uv run pytest tests
   uv build && uvx twine check --strict dist/*
   ```

4. **Rehearse the publication**, optionally, by running the `Publish` workflow
   manually with the `testpypi` target. It builds, publishes to TestPyPI and
   stops before creating a GitHub release.

5. **Merge the pull request**, then tag the merge commit and push the tag. The
   tag is a bare version number and must be annotated and signed:

   ```bash
   git tag -s X.Y.Z -m "iPOPO X.Y.Z"
   git push origin X.Y.Z
   ```

   That push is the release. The `Publish` workflow then builds the artifacts,
   attests their provenance, uploads them to PyPI through Trusted Publishing,
   generates the SBOM and creates the GitHub release — titled `vX.Y.Z`, with
   notes taken from `docs/changelog.md`. None of this is done by hand, and no
   PyPI token is involved.

6. **Verify the result** as a user would, following the *Verifying a release*
   section of `SECURITY.md`.
