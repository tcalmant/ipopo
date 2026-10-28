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

### Support period

The `v3` branch is supported as long as it is the current development line, without a fixed end date.
It is the only branch for which new releases are planned.

Within that branch, support follows the minor version: a minor version keeps receiving security fixes until the next minor version is released, plus **three months** to leave time to upgrade.
For example, once 3.3.0 is released, the 3.2.x line receives security fixes for three more months and is then end of life.

The set of supported Python versions is that of the latest release, listed in the table above and in `pyproject.toml`.
A Python version is dropped once it reaches its own end of life, which is announced in the release notes of the version dropping it.

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

- **Affected version and branch** (e.g. `3.3.0`, `v3`), and the Python version
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
- **No bundle isolation.**
  See "malicious bundles" above.
  Python's single module namespace makes per-bundle isolation infeasible: iPOPO provides lifecycle management, not a security boundary
- **No concurrency limit on network services.**
  The HTTP service spawns a thread per connection without a concurrency cap or rate limiting.
  Since 3.2.2 the HTTP service does bound each individual request, with `pelix.http.max_body_size` (1 MiB by default) and `pelix.http.socket_timeout` (60 seconds by default, applied by the synchronous service only), so a single client can no longer hold a handling thread forever.
  Both limits apply to `read_data()`: a servlet reading the raw stream given by `get_rfile()` has to bound what it reads itself.
  The shells have their own limits: since 3.2.3 the remote shell bounds its clients (`pelix.shell.max_clients`), the length of a line and the time to log in or to stay idle, and since 3.3.0 the XMPP shell gives each session its own thread, with an idle timeout and at most `shell.xmpp.max_sessions` sessions per JID.
  Do not expose the HTTP service to untrusted clients

If you believe one of these is materially worse than described here, that is a report worth making.

## Hardening guidance for deployments

If you are deploying iPOPO in production, and particularly on a network you do not fully control:

- **Keep the HTTP service on loopback.**
  It binds to `127.0.0.1` by default since 3.3.0 (`0.0.0.0` before): put an authenticating reverse proxy in front of it if it must be reachable
- **Put a web application with logins behind a TLS reverse proxy, and tell the HTTP service about it.**
  Set `pelix.http.proxy.trusted` to the proxy address, so that the client address (used by the login throttle) and the scheme (used by the `Origin` check and the `Secure` flag of cookies) are the ones of the client.
  The proxy must keep the `Host` header and overwrite, not forward, the `X-Forwarded-*` headers of its clients.
  Enable `pelix.http.cors.enforce` and `pelix.http.allowed_hosts`: both are off by default for compatibility.
  With the session cookie (`SameSite=Lax`), `pelix.http.cors.enforce` is the protection against cross-site request forgery: there is no CSRF token, and a servlet changing data on a `GET` request is not protected.
  Sessions have a sliding expiration only (`pelix.http.session.max_inactive_interval` without request), and an account removed from the identity store keeps its sessions until they expire
- **Do not expose the remote shell.**
  The `pelix.shell.admin` permission allows installing, starting and stopping arbitrary bundles, which is equivalent to remote code execution.
  It binds to `localhost` by default, keep it that way, or prefer a Unix socket (`pelix.shell.unix.path`) for local administration.
  Since 3.3.0 every TCP client must log in, and each command needs a permission from the security layer: grant `pelix.shell.read` to the users which only need to look.
  If remote administration is required, use the TLS front-end **with certificate-based client authentication** (`pelix.shell.ssl.ca`), documented in `docs/refcards/shell.md`, and restrict it to an administrative network.
  `pelix.shell.ssl.ca` is **not optional** unless `pelix.shell.ssl.client_auth` is `none`: setting `pelix.shell.ssl.cert` without it would make the shell accept any client certificate signed by any authority of the system trust store.
  Since 3.3.0 the shell refuses to start in that case (3.2.2 only logs an error)
- **List the users of the XMPP shell.**
  Since 3.3.0 it only answers the JIDs of `shell.xmpp.users`, and trusts the XMPP server (and the servers it federates with) to authenticate them: prefer a server which only federates over verified TLS, or none
- **Keep TLS verification enabled on the XMPP client.**
  Since 3.3.0 the XMPP shell and `pelix.misc.xmpp` verify the certificate of the server by default: do not set the `shell.xmpp.tls.verify` property to `0`, pass `--no-tls-verify` to `python -m pelix.shell.xmpp`, nor give `ssl_verify=False` to the bots
- **Keep Remote Services and mDNS discovery on trusted network segments only.**
  mDNS discovery accepts input from any host on the local link
- **Validate any externally-derived Configuration Admin PID** before passing it to the Configuration Admin API
- **Run the framework as an unprivileged user**, in a container or under a service manager with restricted capabilities.
  iPOPO does not drop privileges itself
- **Install bundles only from sources you trust**, and prefer pinned versions
- **Watch the releases feed** (https://github.com/tcalmant/ipopo/releases) or subscribe to repository security advisories, so you learn about fixes

## Verifying a release

Starting with 3.2.2, releases are built and published by the `Publish` GitHub Actions workflow, triggered by the push of a signed tag.
Nothing is uploaded from a developer machine, and no long-lived PyPI token exists: the upload is authenticated with a short-lived OpenID Connect token, through [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/).

Four things can be checked independently.

**The PyPI attestations.**
Each file published on PyPI carries a [PEP 740](https://peps.python.org/pep-0740/) attestation, shown in the *Verified details* panel of the project page.
PyPI itself verifies it against the trusted publisher declared for the project, so a file uploaded from anywhere else would not carry it.

**The build provenance.**
The same artifacts are covered by a SLSA provenance attestation, which links them to the workflow run and the commit that produced them:

```bash
gh attestation verify iPOPO-3.2.2.tar.gz --repo tcalmant/ipopo
```

**The release tag.**
Release tags are annotated and signed with the maintainer GPG key:

```bash
git tag -v 3.2.2
```

**The SBOM.**
Every release has a CycloneDX Software Bill of Materials attached to it, as `ipopo-sbom.cdx.json` and `ipopo-sbom.cdx.xml`.
It lists the components iPOPO depends on, so they can be checked against vulnerability databases, and records the SHA-256 digest of each published artifact.

If any of these checks fails on a file you obtained from PyPI or from the GitHub releases page, please report it as described above: the release pipeline and the integrity of the published artifacts are in scope.

## Security advisories

Published advisories are listed at:

> https://github.com/tcalmant/ipopo/security/advisories

Fixes are also noted in the changelog (`docs/changelog.md`) and in the release notes.

## Questions

For questions about this policy that are **not** themselves a vulnerability report, open a regular GitHub issue or discussion.
