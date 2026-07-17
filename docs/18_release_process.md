# Production Release Process

This runbook is the release contract for public Telecraft packages. Release credentials and
Telegram sessions stay local or in protected GitHub environments and are never committed.

## Release lanes

- `0.1.x`: internal milestones; live evidence is optional.
- `0.2.x+` prereleases: public alpha, beta, or release-candidate builds.
- stable: a version without a prerelease suffix and with compatibility/support sign-off.

Every public `0.2.x+` release must pass the live-evidence, packaging, exact-tag artifact, PyPI
provenance, verification, and rollback gates below. TestPyPI is an optional rehearsal and is not a
dependency of the production publishing workflow.

Set `VERSION` without a leading `v`, set `RELEASE_TYPE` to `alpha`, `beta`, `rc`, or `stable`, and
use `v$VERSION` only for the release tag.

## One-time PyPI Trusted Publisher setup

Configure this publisher on the existing `telecraft` project:

| Owner | Repository | Workflow | Environment |
| --- | --- | --- | --- |
| `meniwap` | `telecraftor` | `publish.yml` | `pypi` |

The `pypi` GitHub environment must be restricted to protected release tags and require approval
from its configured reviewer. Production uploads use GitHub OIDC; do not store a long-lived PyPI
token or replace the workflow with a manual `twine upload`.

The separate `testpypi.yml` workflow may be used for an optional rehearsal. It does not supply the
artifact used by `publish.yml` and is not required for a production release.

## 1. Prepare the release change

The release pull request must:

- set the same version in `pyproject.toml` and `src/telecraft/version.py`;
- add a matching `CHANGELOG.md` entry and update public status text;
- document deprecations, removals, migration steps, known limitations, and security impact;
- contain no sessions, credentials, live reports, downloads, captured payloads, or build output;
- package only `src/telecraft` plus the declared public metadata files;
- pass review and all required checks before merge to `main`.

Run the non-live gate:

```bash
./.venv/bin/python tools/check_repo_hygiene.py
./.venv/bin/python -m ruff check src tests tools apps examples
./.venv/bin/python -m mypy src
./.venv/bin/python -m pytest tests/meta -q
./.venv/bin/python -m pytest -m "not live" -q
./.venv/bin/python -m pytest tests/live --collect-only -q
```

## 2. Test the exact candidate commit

Merge the reviewed code to `main`, update the checkout, and verify a clean tree:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
test -z "$(git status --porcelain)"
TESTED_COMMIT="$(git rev-parse HEAD)"
test "$TESTED_COMMIT" = "$(git rev-parse origin/main)"
```

Run the manually approved production-safe core and baseline suites from the dedicated test
account:

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

Follow `docs/11_live_runbook.md`. Raw reports and session files remain ignored local artifacts and
must never be staged.

## 3. Commit the filtered evidence

Record the core and baseline run IDs and generate the filtered manifest:

```bash
./.venv/bin/python tools/release_check.py \
  --version "$VERSION" \
  --release-type "$RELEASE_TYPE" \
  --prod-safe-run-core <run_id_core> \
  --prod-safe-run-baseline <run_id_baseline> \
  --tested-commit "$TESTED_COMMIT" \
  --write-dir "release/evidence/$VERSION"
```

Inspect the manifest. Stage only `release/evidence/$VERSION/release_manifest.json`; keep
`readiness.md`, raw events, summaries, account content, and sessions untracked. One follow-up commit
after `TESTED_COMMIT` is allowed, and it may contain only that manifest. Any other tracked change
invalidates the evidence and requires a new live run.

Validate the evidence-only relationship:

```bash
EVIDENCE_COMMIT="$(git rev-parse HEAD)"
git diff --name-only "$TESTED_COMMIT" "$EVIDENCE_COMMIT"
./.venv/bin/python tools/release_check.py \
  --version "$VERSION" \
  --release-type "$RELEASE_TYPE" \
  --evidence-file "release/evidence/$VERSION/release_manifest.json" \
  --write-dir "/tmp/telecraft-release-check-$VERSION" \
  --dry-run
```

The diff must contain exactly the filtered manifest. Merge the evidence-only commit to `main` and
wait for its required CI checks.

## 4. Local packaging preflight

Build from `EVIDENCE_COMMIT`; these local files are disposable preflight output:

```bash
rm -rf dist build
./.venv/bin/python -m build
./.venv/bin/python -m twine check --strict dist/*
./.venv/bin/python tools/check_repo_hygiene.py --artifacts
```

Require exactly one wheel and one source archive with the target version. Inspect their member
lists, license, metadata, and `py.typed`, and confirm that no app, test, workflow, report, database,
session, environment file, or local runtime artifact is present. Install the wheel in a fresh
environment and verify both `importlib.metadata.version("telecraft")` and
`telecraft.__version__` equal `$VERSION`.

## 5. Tag and publish directly to PyPI

The immutable release tag must point to `EVIDENCE_COMMIT`, and that commit must be contained in
`origin/main`:

```bash
git fetch origin --tags
test "$(git rev-parse "$EVIDENCE_COMMIT")" = "$(git rev-parse origin/main)"
test "$(git tag -l "v$VERSION")" = ""
git tag -a "v$VERSION" "$EVIDENCE_COMMIT" -m "Telecraft $VERSION"
git push origin "v$VERSION"
```

Pushing the tag starts `.github/workflows/publish.yml`. The workflow must:

1. require exact tag/version equality and ancestry from `origin/main`;
2. validate the filtered evidence and evidence-only commit relationship;
3. rerun repository, type, meta, unit, and package gates;
4. build one wheel and one source archive from the exact tag;
5. validate and clean-install that wheel;
6. retain those exact files as the `python-package-distributions` Actions artifact;
7. publish that same retained artifact directly to PyPI through the protected `pypi` environment
   and OIDC, with attestations enabled.

Approve the `pypi` environment only after the build job is green and the workflow summary shows
the expected tag, commit, and version. Never move or reuse a published version tag.

## 6. Verify and announce

After publishing:

1. Confirm the wheel and source archive appear on the production PyPI project.
2. Download both from PyPI and compare their SHA-256 hashes with the retained Actions artifact.
3. Install `telecraft==$VERSION` from production PyPI in a clean environment and verify import and
   version.
4. Inspect PyPI provenance/attestations. Each artifact must bind to `meniwap/telecraftor`,
   `.github/workflows/publish.yml`, the release tag, and the `pypi` environment.
5. Create a GitHub Release after PyPI verification:

   ```bash
   gh release create "v$VERSION" --verify-tag --title "Telecraft $VERSION" --generate-notes
   ```

   Add `--prerelease` only for alpha, beta, or RC versions.
6. Publish notes covering highlights, compatibility/deprecations, supported Python/platforms,
   known limitations, security notes, and upgrade/rollback guidance.

## Rollback, yank, and incident response

PyPI files and versions are immutable. Never rebuild or overwrite a released version.

- **Abort before PyPI:** do not approve the protected environment; delete an unpublished bad tag
  only after confirming no artifact was released, then fix and repeat the affected gates.
- **Broken but safe release:** publish a new patch or prerelease. Yank the bad version when normal
  resolution should avoid it, and document why.
- **Credential or private-data exposure:** stop publishing, preserve minimum sanitized evidence,
  remove exposed files where possible, yank/delete affected public artifacts according to PyPI
  incident policy, rotate/revoke Telegram sessions and credentials, and publish a clean successor.

Branch and tag protection should require pull requests and CI on `main`, reject force pushes and
deletions, protect `v*` tags, limit tag creation to maintainers, and require approval on the `pypi`
environment.
