# Security Policy

iPOPO is a framework for building long-running, modular applications, and several of its subsystems (HTTP service, Pelix Shell, Remote Services, RSA) are network-facing.
Security reports are taken seriously and are welcome.

## Supported versions

Security fixes are provided for the following branches:

| Version | Branch | Python | Status |
| ------- | ------ | ------ | ------ |
| 3.2.x   | `v3`   | 3.10 - 3.15 | Actively maintained: security and bug fixes |
| 2.x     | `v2`   | 2.7, 3.4+ | Abandoned: no fixes |
| 1.x     | `v1`   | 2.7, 3.4+ | Extremely critical fixes only |

The `v2` branch was never completed and has no known production users: it is abandoned rather than superseded.

The `v1` branch is a different case: instances are still deployed in the wild, so extremely critical issues (typically remote code execution or authentication bypass) may still be fixed there, on Python 2.7 if needed.
Anything less severe will not be backported.

Users on `v1` or `v2` are encouraged to migrate to `v3`.

Only the latest release of a supported branch receives fixes.
If you are running an older patch release, upgrade before reporting an issue.

The `v3` branch is the current development line and is where fixes land first.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues, pull requests or discussions.**

### Preferred: GitHub private vulnerability reporting

Report via the repository's **Security** tab -> **Report a vulnerability**:

> https://github.com/tcalmant/ipopo/security/advisories/new

This creates a private advisory visible only to you and the maintainers, allows coordinated disclosure, and can be used to request a CVE identifier once the report is confirmed.

### Alternative: email

If you cannot use GitHub, email **thomas.calmant+github@gmail.com**.

If you wish to encrypt your report, request the maintainer's public key at that address before sending details.

### What to include

The more of this you can provide, the faster the fix:

- **Affected version and branch** (e.g. `3.2.2`, `v3`), and the Python version
- **Affected component** (e.g. `pelix.remote.discovery.mdns`, `pelix.http.basic`, `pelix.shell.remote`)
- **Type of issue**: remote code execution, path traversal, information disclosure, denial of service, authentication bypass, etc.
- **Reproduction steps**, ideally a minimal script or bundle. A failing test case is ideal
- **Impact assessment**: what an attacker gains, and what access they need to start (same host, same LAN, reachable TCP port, authenticated shell user, ...)
- **Any suggested mitigation or patch**, if you have one
- **Whether you intend to publish** anything about the issue, and on what timeline

Reports written in English or French are both fine.

## What to expect

| Stage | Target |
| ----- | ------ |
| Acknowledgement of your report | within **5 business days** |
| Initial assessment (confirmed / not a vulnerability / need more info) | within **10 business days** |
| Fix for critical and high severity issues | within **30 days** of confirmation |
| Fix for medium and low severity issues | next scheduled release |

iPOPO is maintained by a (very) small number of volunteers on a best-effort basis; these are the targets aimed for, not a contractual guarantee.
If a fix is going to take longer than the target (for example because it requires a breaking change to a default) you will be told, and told why.

During the process you can expect to be kept informed of the assessment, the planned fix and the intended disclosure date.

## Disclosure policy

Coordinated disclosure is followed:

1. You report privately
2. The report is confirmed and a fix developed, in private, with you kept in the loop
3. A release containing the fix is published, together with a GitHub Security Advisory and a changelog entry
4. Public disclosure happens **after** the fixed release is available, normally within **90 days** of the initial report

If a vulnerability is already being exploited in the wild, or is already public, the timeline is compressed and mitigation guidance is published as quickly as possible, ahead of a full fix if necessary.

Reporters are credited by name and/or handle in the advisory and changelog, unless you ask to remain anonymous.
There is no bug bounty programme, as iPOPO is a volunteer-maintained open source project, but credit is always given.

## Scope

### In scope

- The `pelix` package as published on PyPI, on all supported branches, including all the services it bundles
- The documented default configuration of any of the above
- The build and release pipeline (`.github/workflows/`), and the integrity of published artifacts

### Out of scope

- **Third-party dependencies.** Report those to their own maintainers. If iPOPO's *use* of a dependency is what creates the vulnerability, that is in scope, please do report it
- **Vulnerabilities in application code built with iPOPO**, including servlets, components and services written by users, unless a framework API makes the insecure behavior unavoidable or is misleading about its guarantees
- **Malicious bundles.** iPOPO has no sandbox or permission model.
  A bundle installed into a framework runs with the full privileges of the host process and can do anything that process can.
  Installing an untrusted bundle is equivalent to executing untrusted code: treat bundle sources as you would any other code you run.
  Reports that a malicious bundle can compromise the framework are not vulnerabilities
- Findings from automated scanners submitted without a demonstrated impact on iPOPO
- Attacks requiring physical access to the host, or an already-compromised host
- Social engineering of maintainers or users

### Known design limitations

The following are **current, documented behaviors** rather than unreported vulnerabilities.
They are known and tracked, and they do **not** need to be reported, but a *specific, novel* exploitation technique against them is still worth reporting.

- **Remote Services and RSA transports are unauthenticated.**
  The JSON-RPC and XML-RPC servlets and the dispatcher servlet (`/pelix-dispatcher`) perform no authentication or authorization.
  Any client that can reach the port can enumerate and invoke exported services.
  Authentication support is planned.
  Until then, exported services must only be reachable on a trusted network or behind an authenticating reverse proxy
- **The HTTP service binds to `0.0.0.0` by default.**
  This is long-standing, documented behavior and is not going to change: too much existing code depends on it.
  Set the `pelix.http.address` property to `127.0.0.1` unless external exposure is intended
- **No bundle isolation.**
  See "malicious bundles" above.
  Python's single module namespace makes per-bundle isolation infeasible: iPOPO provides lifecycle management, not a security boundary
- **No concurrency limit on network services.**
  The HTTP service and remote shell spawn a thread per connection without a concurrency cap or rate limiting.
  Since 3.2.2 the HTTP service does bound each individual request, with `pelix.http.max_body_size` (1 MiB by default) and `pelix.http.socket_timeout` (60 seconds by default, applied by the synchronous service only), so a single client can no longer hold a handling thread forever.
  Both limits apply to `read_data()`: a servlet reading the raw stream given by `get_rfile()` has to bound what it reads itself.
  The remote shell has no equivalent limits.
  Do not expose either to untrusted clients

If you believe one of these is materially worse than described here, that is a report worth making.

## Hardening guidance for deployments

If you are deploying iPOPO in production, and particularly on a network you do not fully control:

- **Bind the HTTP service to loopback.**
  Set `pelix.http.address` to `127.0.0.1` and put an authenticating reverse proxy in front of it if it must be reachable
- **Do not expose the remote shell.**
  It allows installing, starting and stopping arbitrary bundles, which is equivalent to remote code execution.
  It binds to `localhost` by default, keep it that way.
  If remote administration is required, use the TLS front-end **with certificate-based client authentication** (`pelix.shell.ssl.ca`), documented in `docs/refcards/shell.md`, and restrict it to an administrative network.
  `pelix.shell.ssl.ca` is **not optional**: setting `pelix.shell.ssl.cert` without it makes the shell accept any client certificate signed by any authority of the system trust store.
  Since 3.2.2 this is logged as an error; it will be refused in 3.3.0
- **Enable TLS verification on the XMPP client.**
  Set the `shell.xmpp.tls.verify` property of the XMPP shell to `1`, or pass `--tls-verify` to `python -m pelix.shell.xmpp`.
  When using `pelix.misc.xmpp` directly, pass `ssl_verify=True`.
  The default does not verify server certificates; it will become `1` in 3.3.0
- **Keep Remote Services and mDNS discovery on trusted network segments only.**
  mDNS discovery accepts input from any host on the local link
- **Validate any externally-derived Configuration Admin PID** before passing it to the Configuration Admin API
- **Run the framework as an unprivileged user**, in a container or under a service manager with restricted capabilities.
  iPOPO does not drop privileges itself
- **Install bundles only from sources you trust**, and prefer pinned versions
- **Watch the releases feed** (https://github.com/tcalmant/ipopo/releases) or subscribe to repository security advisories, so you learn about fixes

## Security advisories

Published advisories are listed at:

> https://github.com/tcalmant/ipopo/security/advisories

Fixes are also noted in the changelog (`docs/changelog.md`) and in the release notes.

## Questions

For questions about this policy that are **not** themselves a vulnerability report, open a regular GitHub issue or discussion.
