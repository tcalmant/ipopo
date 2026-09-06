# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

iPOPO is a Service-Oriented Component Model (SOCM) for Python, built on top of Pelix, a dynamic
service platform (an OSGi/iPOJO-inspired framework in pure Python). This is the `v3` branch,
targeting Python 3.10+. It is not backward compatible with the `v1`/`v2` branches (separate git
branches), though application code written for v1 mostly still runs on v3.

## Commands

```bash
# Setup (uv manages the virtual environment, dependencies and Python versions)
uv sync --all-extras   # project + every optional dependency + dev tools

# Run the full test suite (as CI does)
uv run coverage run -m pytest tests
uv run coverage combine

# Or simply
uv run python -m pytest tests

# Run a single test module / class / test
uv run python -m pytest tests/framework/test_framework.py
uv run python -m pytest tests/ipopo/test_ipopo_service.py::SomeTestCase::test_something

# Lint / format / type-check (per CONTRIBUTING.md; this is exactly what CI enforces)
uv run ruff check .
uv run ruff format --check .
uv run ty check pelix tests

# Try the Pelix shell
uv run python -m pelix.shell --version
uv run python -m pelix.shell

# Build the documentation (as Read the Docs / CI do; docs/requirements.txt is its own,
# separate dependency set, not part of the main uv sync)
uv venv .venv-docs
uv pip install --python .venv-docs/bin/python -r docs/requirements.txt
.venv-docs/bin/sphinx-build -W --keep-going -b html docs docs/_build/html
```

Test files are named `test_*.py` (not `*_test.py`), mirroring the module they cover.

Some test suites (parts of `tests/remote`, `tests/rsa`, `tests/misc`, `tests/services`, `tests/shell`)
depend on external services (etcd2, etcd3, an MQTT broker, Redis, an XMPP server, ZooKeeper) brought
up via `tests-infra/compose.yaml` (`docker compose -f tests-infra/compose.yaml up -d`, then
`sh ./tests-infra/xmpp/docker_register_users.sh`). Without that infrastructure, those tests will fail
or be skipped depending on the module.

## Architecture

### Pelix (the framework layer, `pelix/framework.py`, `pelix/constants.py`)

Pelix provides the OSGi-like runtime concepts that everything else builds on:

- **Framework**: singleton-ish root object (`FrameworkFactory.get_framework()`), itself a `Bundle`.
  Manages the bundle registry, the service registry, and dispatches framework/bundle/service events.
- **Bundle**: a Python module with a lifecycle (`INSTALLED` -> `RESOLVED` -> `STARTING` -> `ACTIVE` ->
  `STOPPING` -> `UNINSTALLED`). A bundle can define a module-level object named via the `ACTIVATOR`
  constant, decorated with `@BundleActivator`, implementing `start(context)` / `stop(context)`.
  Updating a bundle uses `importlib.reload`.
- **BundleContext**: the handle a bundle/component uses to interact with the framework (install/start
  bundles, register services, look up/track services, listen for events).
- **Service registry**: services are plain objects registered against one or more specification
  strings plus a properties dict (`objectClass`, `service.id`, `service.ranking`, ...). Consumers
  look up services by specification and an optional LDAP-style filter (`pelix/ldapfilter.py`),
  selecting by highest ranking / lowest (oldest) service ID on ties.

### iPOPO (the component model layer, `pelix/ipopo/`)

iPOPO sits on top of Pelix and adds *components*: managed instances of factories (classes) whose
service dependencies are injected and whose lifecycle (`@Validate`/`@Invalidate`) is driven by
whether all required dependencies are currently satisfied.

- `pelix/ipopo/decorators.py`: the public decorator API (`@ComponentFactory`, `@Provides`,
  `@Requires`, `@Instantiate`, `@Validate`, `@Invalidate`, `@Property`, etc.) that manipulates
  factory classes and registers metadata used at instantiation time.
- `pelix/ipopo/handlers/`: pluggable handlers implementing the behavior each decorator declares
  (dependency injection, service registration/unregistration, property binding, ...). New
  dependency/injection behaviors are typically added as a new handler here.
- `pelix/ipopo/core.py`: the iPOPO service implementation (component factory registry, instance
  lifecycle state machine, wiring handlers together).
- `pelix/ipopo/contexts.py`: factory/component context objects carrying the manipulated metadata.
- `pelix/ipopo/constants.py`: iPOPO-specific constants/specification name for `use_ipopo`, the
  iPOPO service one uses to instantiate/kill components programmatically.
- `pelix/ipopo/waiting.py`: helper to wait for component instances to become valid.

Services can be declared with a Python `typing.Protocol` decorated with `@Specification("name")`
(preferred in v3, gives IDE/type-checking benefits) or with a plain string specification name (v1
style, still supported).

### Bundled services (each is itself a set of Pelix bundles/iPOPO components, not core framework code)

- `pelix/shell/`: the Pelix Shell. `parser.py`/`core.py` implement the interpreter and shell core
  service; `console.py`/`remote.py`/`xmpp.py` are front-ends (local console, remote TCP/TLS, XMPP);
  `ipopo.py`, `configadmin.py`, `eventadmin.py`, `report.py`, `log.py`, `beans.py` are command
  providers; `completion/` holds completion providers.
- `pelix/http/`: HTTP service abstraction with a servlet concept (Java-inspired) on top of the
  stdlib HTTP server (`basic.py`, `basic_async.py`); `routing.py` adds decorator-based REST-like
  routing.
- `pelix/remote/`: Remote Services, export/import of services between Pelix frameworks
  (`dispatcher.py`, `registry.py`, transport implementations under `remote/transport/` and
  discovery under `remote/discovery/`, plus JSON-RPC/XML-RPC support).
- `pelix/rsa/`: Remote Service Admin (OSGi RSA spec), interoperates with both iPOPO and Java OSGi
  frameworks; `providers/` and `topologymanagers/` hold pluggable RSA providers/topology managers.
- `pelix/services/`: other OSGi-inspired services: Configuration Admin (`configadmin.py`), Event
  Admin (`eventadmin.py`, `eventadmin_mqtt.py`), file install (`fileinstall.py`), MQTT (`mqtt.py`).
- `pelix/misc/`: smaller standalone utilities/services (XMPP client, MQTT client, jabsorb
  serialization, SSL wrapping, an EventAdmin-to-console printer, `init_handler.py`).
- `pelix/security/`: authentication and authorization layer, transport-neutral (usable from HTTP,
  the shell, MQTT, ...). `core.py` implements `authenticate()` (turns credentials into a
  `Subject` via `Authenticator`/`MembershipProvider` services) and the `Authorization` facade
  combining `Authorizer` services; `decorators.py` provides `@AllowGroup`/`@AllowPermission`-style
  declarative guards; `policy.py` reads a TOML role/permission policy file; `htpasswd.py` and
  `_crypt.py` implement an Apache `.htpasswd`/`.htgroup` credential store, including its hash
  verification (SHA, apr1, SHA-crypt, bcrypt if installed). Stated non-goal: no code-level
  sandboxing against locally installed bundles, only against remote callers.

### Tests

`tests/` mirrors the `pelix/` package layout (`tests/framework`, `tests/ipopo`, `tests/http`,
`tests/remote`, `tests/rsa`, `tests/security`, `tests/services`, `tests/misc`, `tests/shell`,
`tests/dataclasses`).
Tests are written with `unittest.TestCase` classes and run through `pytest`. `samples/hello_world`
contains the runnable specification/provider/consumer example referenced in the README.

## Code style (from CONTRIBUTING.md)

- Python 3.10+ compatible; use type hints throughout; prefer typed `Protocol` service
  specifications over bare specification-name strings in new code.
- Every module must define `__version_info__` (tuple) and a matching `__version__` string.
- Imports go after the module docstring and before any other code; remove unused imports.
- Use `logging`, never `print`, for diagnostics.
- Formatting and lint follow `ruff` (line length 110, see the `[tool.ruff]` table in
  `pyproject.toml`), with the `I` (isort) rule set enabled; `ty` does the type checking. There is
  no `black` dependency in this project.
- Naming: `CamelCase` classes, `SNAKE_UPPERCASE` constants, `snake_case` methods; first instance
  method arg is `self`, first classmethod arg is `cls`.
- New feature code goes into an existing or new `pelix` subpackage: do not add new modules
  directly under the top-level `pelix` package. Matching tests go under `tests/<subpackage>`.
- New feature docs go into `docs/refcards` (Sphinx, reStructuredText or MyST Markdown).

### Text and comments

- ASCII punctuation only in code comments and Markdown: no en/em dash (use a plain dash, a colon,
  or parenthesis instead), no curly quotes, no other non-ASCII punctuation.
- Comments explain *why*, not *what*.
