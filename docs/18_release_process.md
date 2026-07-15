# Release Process

This is the production release runbook for Telecraft. Public publishing uses GitHub Actions and
PyPI Trusted Publishing (OIDC); long-lived PyPI credentials must not be stored in the repository or
GitHub secrets.

## Release lines

- `0.1.x`: internal milestones; live evidence is optional.
- `0.2.x+` prereleases: public alpha, beta, or release-candidate builds.
- stable: a version with no prerelease suffix; every production gate below is mandatory.

Set `VERSION` without a leading `v`, set `RELEASE_TYPE` to `alpha`, `beta`, `rc`, or `stable`, and
use `v$VERSION` only for the release tag.

## 1. Prepare and merge the release candidate

The release-candidate pull request must:

- set the same version in `pyproject.toml`;
- add a matching `CHANGELOG.md` entry;
- document deprecations, removals, migration steps, known limitations, and security impact;
- contain no sessions, credentials, live reports, downloads, captured payloads, or build output;
- pass review and all required checks before merge to `main`.

Run the non-live gate from a clean checkout:

```bash
./.venv/bin/python tools/check_repo_hygiene.py
./.venv/bin/python -m ruff check src tests tools apps examples
./.venv/bin/python -m mypy src
./.venv/bin/python -m pytest tests/meta -q
./.venv/bin/python -m pytest -m "not live" -q
./.venv/bin/python -m pytest tests/live --collect-only -q
```

The meta gate enforces that Tier A exactly matches the stable methods mapped in
`tests/meta/v2_live_evidence_map.json`.

## 2. Test the exact candidate commit

Update `main`, confirm the checkout is clean and matches the reviewed remote commit, and capture its
full SHA before starting a live run:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
test -z "$(git status --porcelain)"
TESTED_COMMIT="$(git rev-parse HEAD)"
test "$TESTED_COMMIT" = "$(git rev-parse origin/main)"
```

`TESTED_COMMIT` is the code/configuration commit exercised by the evidence. Do not change tracked
files while collecting evidence. Public `0.2.x+` releases require the manually approved prod-safe
core and baseline suites from a dedicated test account:

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

Follow `docs/11_live_runbook.md`. Raw reports and session files stay in ignored local directories;
they must never be staged.

## 3. Generate the filtered evidence commit

Record the core and baseline run IDs. Generate the tracked, filtered release manifest directly
under the release evidence directory:

```bash
./.venv/bin/python tools/release_check.py \
  --version "$VERSION" \
  --release-type "$RELEASE_TYPE" \
  --prod-safe-run-core <run_id_core> \
  --prod-safe-run-baseline <run_id_baseline> \
  --tested-commit "$TESTED_COMMIT" \
  --write-dir "release/evidence/$VERSION"
```

The checker requires the exact step order from `tests/meta/v2_live_evidence_map.json`, zero failed
steps, zero cleanup errors, complete health probes, and valid static release checks. The generated
manifest contains the full `tested_commit`, each run's matching source commit and clean-tree flag,
run IDs, counts, step names, probe summaries, and a SHA-256 digest for each local live-evidence
bundle. Generation also checks that the current checkout is clean and that `HEAD` equals
`TESTED_COMMIT`; a typed SHA alone is not accepted. The bundle digest identifies the live evidence;
it is not a hash of the Python wheel or source archive.

Inspect `release/evidence/$VERSION/release_manifest.json` and `readiness.md`. The manifest is
designed to omit raw events, report prose, message/account content, and session data, but inspection
is still required. Stage only `release_manifest.json`; `readiness.md` is local review output and
must be removed or left untracked. Do not hand-edit the manifest.

One follow-up commit after `TESTED_COMMIT` is allowed, and it may contain exactly
`release/evidence/$VERSION/release_manifest.json`. The evidence commit does not claim that untested
code changes are safe. If any other file changes, including code, configuration, workflow,
documentation, version, or changelog files, discard the evidence and repeat the live run from the
new commit.

After committing only the evidence directory, verify the relationship and revalidate the filtered
manifest:

```bash
EVIDENCE_COMMIT="$(git rev-parse HEAD)"
git merge-base --is-ancestor "$TESTED_COMMIT" "$EVIDENCE_COMMIT"
git diff --name-only "$TESTED_COMMIT" "$EVIDENCE_COMMIT"
./.venv/bin/python tools/release_check.py \
  --version "$VERSION" \
  --release-type "$RELEASE_TYPE" \
  --evidence-file "release/evidence/$VERSION/release_manifest.json" \
  --write-dir "/tmp/telecraft-release-check-$VERSION" \
  --dry-run
```

The diff output must contain exactly
`release/evidence/$VERSION/release_manifest.json`. Required CI must also pass on
`EVIDENCE_COMMIT`.

## 4. Local packaging preflight

Build locally from `EVIDENCE_COMMIT` to catch packaging errors. These local files are disposable
preflight output and are not the files later uploaded to either package index.

```bash
rm -rf dist build
./.venv/bin/python -m build
./.venv/bin/python -m twine check --strict dist/*
./.venv/bin/python tools/check_repo_hygiene.py --artifacts
```

Inspect the wheel and source archive for the intended license, metadata, typed-package marker, and
package files, with no local/runtime artifacts. Then install the wheel in a fresh environment:

```bash
python -m venv /tmp/telecraft-release-smoke
/tmp/telecraft-release-smoke/bin/python -m pip install --upgrade pip
/tmp/telecraft-release-smoke/bin/python -m pip install dist/*.whl
/tmp/telecraft-release-smoke/bin/python -c \
  "from importlib.metadata import version; import telecraft; assert version('telecraft') == '$VERSION'"
```

Use an equivalent temporary path and `Scripts\python` on Windows. Remove the environment after the
check.

## 5. Build once and approve on TestPyPI

Dispatch the TestPyPI workflow from `main` while it points to `EVIDENCE_COMMIT`. The `testpypi`
GitHub environment is restricted to `main` and requires approval from its configured reviewer.
Trusted Publishing binds the upload to the expected repository, workflow, and environment.

The TestPyPI workflow is the start of artifact promotion, not an unrelated rehearsal. It must:

1. revalidate the filtered evidence and commit relationship;
2. build the wheel and source archive once from `EVIDENCE_COMMIT`;
3. run `twine check --strict` and artifact hygiene;
4. record the exact distribution files and their SHA-256 hashes as the approved candidate bundle;
5. retain the immutable GitHub Actions artifact for 30 days and publish that same bundle to
   TestPyPI through OIDC;
6. download the TestPyPI wheel without resolving dependencies there, install it with dependencies
   from production PyPI, hash-compare both TestPyPI files to the retained artifact, and verify
   import and version.

The workflow writes its run ID, commit SHA, version, and candidate hashes to the job summary. Record
them in the release review.
TestPyPI versions are immutable, so use a new release version when a prior candidate already exists.
If the TestPyPI smoke fails or the candidate commit must change, do not tag; fix the problem and
repeat from the appropriate earlier gate. A later unrelated commit on `main` does not change the
candidate, but the release tag must still point to the exact tested TestPyPI commit.

## 6. Tag and promote the same artifacts to PyPI

The release tag must point to the exact `EVIDENCE_COMMIT` used by the approved TestPyPI run. That
commit must be contained in `origin/main`, although a later unrelated commit may already be the tip
of `main`.

Before tagging, confirm:

- `VERSION`, release type, changelog heading, package metadata, and `v$VERSION` agree;
- the tag does not already exist locally or remotely;
- `tested_commit` is an ancestor of the tag commit and the intervening diff is evidence-only;
- required CI passed on both the tested candidate and evidence commit;
- exactly one TestPyPI workflow run succeeded for the tag commit, its retained candidate artifact
  is unexpired, and the TestPyPI smoke matched both downloaded files to that artifact's hashes;
- no unresolved release-blocking security advisory or regression exists;
- branch and tag rules prevent deletion and force-push.

```bash
git fetch origin --tags
test "$(git rev-parse "$EVIDENCE_COMMIT")" = "$(git rev-parse <testpypi-run-commit>)"
test "$(git tag -l "v$VERSION")" = ""
git tag -a "v$VERSION" "$EVIDENCE_COMMIT" -m "Telecraft $VERSION"
git push origin "v$VERSION"
```

The production workflow re-checks tag/version equality, main ancestry, filtered evidence, and the
evidence-only diff. It locates exactly one successful TestPyPI workflow for the tag commit, resolves
that run's immutable artifact ID, requires it to be unexpired, downloads the retained wheel and
source archive by artifact ID, validates them, and publishes those bytes to PyPI. The successful
TestPyPI smoke already proved those retained bytes match the files served by TestPyPI. A local build
may run as an additional packaging check, but its output must not replace, rebuild, or repackage
either promoted file. Push the tag within the 30-day artifact-retention window; after expiry, fail
closed and prepare a new release version instead of weakening the provenance check.

The `pypi` GitHub environment is restricted to release tags and requires approval from its
configured reviewer. Approval is a final human gate after automated verification, not a replacement
for it. Never move or reuse a published version tag.

## 7. Verify and announce

After publishing:

1. Confirm both wheel and source archive appear on PyPI and install from the production index in a
   fresh environment.
2. Confirm the PyPI hashes exactly match the recorded TestPyPI candidate bundle.
3. Inspect each PyPI provenance/attestation record. It must bind the artifact digest to
   `meniwap/telecraftor`, the expected publishing workflow, release tag, and `pypi` environment.
4. Confirm the GitHub release points to the immutable tag and marks prereleases correctly.
5. Publish release notes covering highlights, compatibility/deprecations, supported Python and
   platforms, known limitations, security notes, and upgrade/rollback guidance.
6. Monitor installation failures and security reports during the initial release window.

## Rollback, yank, and hotfix

PyPI files and versions are immutable. Never rebuild or overwrite a released version.

- **Abort before PyPI:** stop promotion, keep the TestPyPI result for diagnosis, do not move the
  tag, fix on a new commit/version as needed, and repeat every affected gate.
- **Broken but safe release:** publish a new patch or prerelease. Yank the bad version when normal
  dependency resolution would cause substantial breakage.
- **Security or destructive defect:** pause announcements, open a private advisory, assess affected
  credentials/sessions and artifacts, yank the release with a clear reason, and prepare a new
  version through the full gate. Recommend revocation or rotation when exposure is possible.
- **Hotfix:** use a new version, keep the change minimal, add a regression test and changelog entry,
  and repeat live evidence where required, TestPyPI approval, exact-artifact promotion, and
  attestation checks. An emergency does not justify reusing a version.

Yanking is preferred to deleting a release because exact-version installs remain possible for
forensics and recovery. Remove an artifact only when PyPI administrators require it or the content
itself exposes credentials, personal data, or unlawful material.

## Incident response

For a suspected release or publishing compromise:

1. stop or disable publishing and preserve workflow run IDs, logs, commit/tag IDs, candidate hashes,
   and attestation data without copying secrets into issues;
2. use a private GitHub security advisory and follow `SECURITY.md`;
3. revoke exposed Telegram sessions, bot tokens, API credentials, GitHub credentials, or PyPI
   recovery material as applicable; OIDC publishing normally leaves no long-lived PyPI token;
4. audit branch/tag changes, environment approvals, workflow provenance, installed Actions, the
   TestPyPI candidate bundle, and all released artifacts;
5. notify affected users with concrete versions, impact, containment, and upgrade/revocation steps;
6. publish a new fixed version and a post-incident review after containment.

Manual `twine upload` is not the normal production path because it bypasses the reviewed promotion
chain. A break-glass exception requires explicit maintainer approval, the already approved candidate
files and matching hashes, short-lived scoped credentials, preserved audit evidence, and all other
release gates.
