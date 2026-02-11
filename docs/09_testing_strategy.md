# Testing strategy

## Unit tests (fast)

- `tests/unit/client/v2/**`: wrapper contracts for every V2 public method
  - dedicated namespace files:
    - `test_games_api.py`, `test_saved_api.py`, `test_stars_api.py`, `test_gifts_api.py`
    - `test_dialogs_api.py`, `test_stickers_api.py`, `test_topics_api.py`, `test_reactions_api.py`
    - `test_privacy_api.py`, `test_notifications_api.py`, `test_business_api.py`
    - `test_stories_api.py`, `test_chatlists_api.py`, `test_channels_api.py`
  - helper type contracts: `test_ref_builders_api.py`
- `tests/unit/client/core/**`: client core wiring/import contracts
- `tests/unit/bot/**`: router/dispatcher/event mapping behavior
- `tests/unit/mtproto/**`: protocol-layer behavior (no live network)
- `tests/meta/**`: coverage/governance gates (`v2_method_matrix.yaml`)

## Live tests (manual, destructive-capable)

- `tests/live/core/**`: core live lane without second account (`-m "live and live_core"`)
- `tests/live/second_account/**`: `@meniwap` membership lane only (`-m "live_second_account"`)
- `tests/live/optional/**`: unstable/expensive lane (`-m "live_optional"`)
- `tests/live/optional/test_live_gifts_paid.py`: paid lane (requires `--live-paid`)
- `tests/live/optional/test_live_business_suite.py`: business lane (requires `--live-business`)
- `tests/live/optional/test_live_chatlists_suite.py`: chatlists lane (requires `--live-chatlists`)
- `tests/live/optional/test_live_stories_write_suite.py`: stories write lane (requires `--live-stories-write`)
- `tests/live/optional/test_live_channels_admin_suite.py`: channel admin lane (requires `--live-channel-admin`)
- all live lanes are gated by `--run-live`
- live runtime defaults to sandbox (`--live-runtime sandbox`)
- prod live requires both `--allow-prod-live` and `TELECRAFT_ALLOW_PROD_LIVE=1`
- destructive operations require `--live-destructive`
- second-account lane additionally requires `--live-second-account <username>`
- paid steps additionally require `--live-paid`
- business lane additionally requires `--live-business`
- chatlists lane additionally requires `--live-chatlists`
- stories write lane additionally requires `--live-stories-write`
- channel admin lane additionally requires `--live-channel-admin`
- audit trail is written to Telegram + local report files (`reports/live/<runtime>/<run_id>/`)

## Governance

- source of truth: `tests/meta/v2_method_matrix.yaml`
- each wrapper method must have a matrix row with stability + lane + required scenarios
- naming convention enforced: `test_<namespace>__<method>__<scenario>`
- compatibility policy: additive changes + explicit deprecation windows
