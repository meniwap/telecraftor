# Release Process

This document defines the manual process for Telecraft release readiness.
Public beta releases may be published to GitHub Releases and PyPI after the release gate passes.
PyPI publishing uses Trusted Publishing through GitHub Actions, not stored PyPI credentials.

## Release Lines

- `0.1.x`: internal milestones; live artifacts are optional.
- `0.2.x+`: public line; prod-safe live evidence is required.

## Internal 0.1.x Gate

```bash
./.venv/bin/python tools/check_repo_hygiene.py
./.venv/bin/python -m ruff check src tests tools apps examples
./.venv/bin/python -m mypy src
./.venv/bin/python -m pytest tests/meta -q
./.venv/bin/python -m pytest -m "not live" -q
./.venv/bin/python -m pytest tests/live --collect-only -q
./.venv/bin/python -m build
./.venv/bin/python tools/check_repo_hygiene.py --artifacts
```

## Public 0.2.x+ Gate

Public releases require the internal gate plus manually approved prod-safe live evidence:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 ./.venv/bin/python -m pytest tests/live \
  -m "live and live_prod_safe" \
  -vv -s \
  --run-live \
  --allow-prod-live \
  --live-profile prod_safe \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Record the run IDs for the core smoke and baseline artifacts, then validate:

```bash
./.venv/bin/python tools/release_check.py \
  --version 0.2.0b4 \
  --release-type beta \
  --prod-safe-run-core <run_id_core> \
  --prod-safe-run-baseline <run_id_baseline> \
  --write-dir reports/releases/0.2.0b4
```

`tools/release_check.py` always validates version, changelog, support contract, and deprecations.
It requires live artifact IDs only for public `0.2.x+` release lines.
If release readiness output is written to a tracked path, include it in the release prep commit.
If it is written under ignored `reports/` paths, verify it is not staged before tagging.

## PyPI Trusted Publishing

Before pushing a release tag for a project that does not exist on PyPI yet, create a pending
trusted publisher in PyPI:

- PyPI project name: `telecraft`
- owner: `meniwap`
- repository: `telecraftor`
- workflow filename: `publish.yml`
- environment: `pypi`

Do not store a PyPI API token, username, or password in GitHub secrets. The release workflow uses
GitHub Actions OIDC with `pypa/gh-action-pypi-publish@release/v1`.

## Public Beta Release

After all gates pass:

```bash
git tag v0.2.0b4
git push origin main
git push origin v0.2.0b4
```

Pushing the version tag triggers the PyPI publish workflow. Create a GitHub prerelease using the
changelog entry and include that this beta is MTProto-only, with no HTTP Bot API module.

## Emergency Manual Upload

Manual `twine` upload is a break-glass fallback only. Prefer the Trusted Publishing workflow for
normal releases, and do not add long-lived PyPI credentials to GitHub.

## Abort Rules

Abort the release if any gate fails, if the changelog/version mismatch, or if
`tools/release_check.py` reports blockers. Do not tag a release until readiness is green.
