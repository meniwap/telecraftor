# 2026-08-06 History Cleanup Record

This record preserves release metadata only. It intentionally contains no captured payload,
credential, session material, or private file content.

## Original Git provenance

The affected public version tags are deleted during local cleanup instead of being silently moved
to rewritten commits. Any clean-history successor must use a new tag and version.

| Ref | Original tag object | Original commit | Original tree |
| --- | --- | --- | --- |
| `v0.2.0b1` | `2b86ac4feccf75f7d8ac21fb0f0c45d2e3b746cf` | `63c33fb44717d4ebfc6c2a742480fe3e6898b30c` | `ce4a52fb4708108a66daca40e99dd1baf6558259` |
| `v0.2.0b2` | `04f7aa0164a7d694a8ab7d2b403dd25b03d801e6` | `d9241b76f6f88de03cf0bdb5659f91d2162a75d0` | `255eac70c46759efcbdf677edd25a207a3fc60e2` |
| `v0.2.0b3` | lightweight | `f8a94cbb2b644e4f1df798031a1d50a99bedd631` | `0ae0b612d8e8c1cb78ce57fdaf409599e21f8acd` |
| `v0.2.0b4` | `3d045296281dbeb1c085fdc428890b57dd05f1f2` | `b778bc7e192731e0a3256d1b3d386a048ae2e73a` | `f5d5822b956a5f2930a2569b840e1274c5df2faa` |
| `v0.2.0` | `cae2cffc7d9d161220031cc110f942baf430c125` | `c6370b6e9fd0070f55b93ae381596211cc273f22` | `05b15b57b108e6d4bce9aa2fa4fbbb94beb1c4cb` |

The local `v0.8.0` recovery tag was not a published package version. Its original tag object was
`c2c2e5e4880b8613a5e5c7d8957246d14d32b323`; it is removed as misleading rather than rewritten.

## Original PyPI artifacts

PyPI exposed exactly `0.2.0b3`, `0.2.0b4`, and `0.2.0` when this record was captured. All files
were not yanked and had PyPI Integrity attestations binding them to GitHub Actions repository
`meniwap/telecraftor`, workflow `publish.yml`, and environment `pypi`.

| Version | Artifact | SHA-256 | Provenance |
| --- | --- | --- | --- |
| `0.2.0b3` | `telecraft-0.2.0b3-py3-none-any.whl` | `4be07e5bfd1b17845383c1e2d2e086e2eda834cdb9b5672bec62dbcdbf2b407d` | [PyPI](https://pypi.org/integrity/telecraft/0.2.0b3/telecraft-0.2.0b3-py3-none-any.whl/provenance) |
| `0.2.0b3` | `telecraft-0.2.0b3.tar.gz` | `f053deb551fc759bb604480da17770d5ea7404d5f12880a2b65d25fa0c1617cd` | [PyPI](https://pypi.org/integrity/telecraft/0.2.0b3/telecraft-0.2.0b3.tar.gz/provenance) |
| `0.2.0b4` | `telecraft-0.2.0b4-py3-none-any.whl` | `63090bf8a00929184d1b0a3d9461102dbc095fcbb235dcb8b122f58be0986377` | [PyPI](https://pypi.org/integrity/telecraft/0.2.0b4/telecraft-0.2.0b4-py3-none-any.whl/provenance) |
| `0.2.0b4` | `telecraft-0.2.0b4.tar.gz` | `6e893d1256d7047d095c10814358226b8bf57f0092b53daa19c3c85e9bb33c41` | [PyPI](https://pypi.org/integrity/telecraft/0.2.0b4/telecraft-0.2.0b4.tar.gz/provenance) |
| `0.2.0` | `telecraft-0.2.0-py3-none-any.whl` | `9e0ca0fca49dedd849da3b22363852ba8156aa61892ca1291fd40a312d9a0b05` | [PyPI](https://pypi.org/integrity/telecraft/0.2.0/telecraft-0.2.0-py3-none-any.whl/provenance) |
| `0.2.0` | `telecraft-0.2.0.tar.gz` | `1913b177e24ea31a4ec8f3235adef6f8aab547f41b132c75d757b537b8523a13` | [PyPI](https://pypi.org/integrity/telecraft/0.2.0/telecraft-0.2.0.tar.gz/provenance) |

Historical `0.2.0b3` and `0.2.0b4` distributions require separate PyPI incident cleanup because
rewriting Git cannot alter already published files. Do not republish any existing version.

## Purge scope and external boundary

The local rewrite removes `.telecraft/`, `apps/bot_config.json`, `apps/manual_labs/`,
`apps/streamingbot/`, `downloads/`, `reports/`, and `tests/unit/fixtures/tl/` from every retained
commit. The rewrite must then expire reflogs, prune unreachable objects, and pass both history
gates.

This local operation does not change GitHub. Remote branches, tags, Releases, caches, forks,
Actions artifacts, and PyPI files remain separate cleanup surfaces. Replacing the remote history
requires an explicit coordinated force-push after collaborators have been warned and protections
have been handled.
