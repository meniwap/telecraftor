# Testing strategy

## Unit tests (fast)

- `tests/unit/client/v2/**`: wrapper contracts for every V2 public method
  - dedicated namespace files:
    - `test_games_api.py`, `test_saved_api.py`, `test_stars_api.py`, `test_gifts_api.py`
    - `test_dialogs_api.py`, `test_stickers_api.py`, `test_topics_api.py`, `test_reactions_api.py`
    - `test_privacy_api.py`, `test_notifications_api.py`, `test_business_api.py`
    - `test_stories_api.py`, `test_chatlists_api.py`, `test_channels_api.py`
    - `test_search_api.py`, `test_drafts_api.py`, `test_reports_api.py`
    - `test_stats_api.py`, `test_discovery_api.py`, `test_account_api.py`
    - `test_calls_api.py`, `test_takeout_api.py`, `test_webapps_api.py`
    - `test_todos_api.py`, `test_translate_api.py`
  - helper type contracts: `test_ref_builders_api.py`
  - helper type contracts (v4): `test_ref_builders_account_calls_takeout.py`
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
- `tests/live/optional/test_live_calls_readonly_suite.py`: calls readonly lane (requires `--live-calls`)
- `tests/live/optional/test_live_calls_write_suite.py`: calls write lane (requires `--live-calls-write`)
- `tests/live/optional/test_live_takeout_suite.py`: takeout lane (requires `--live-takeout`)
- `tests/live/optional/test_live_webapps_suite.py`: webapps lane (requires `--live-webapps`)
- `tests/live/optional/test_live_stats_readonly_suite.py`: stats readonly lane (requires `--live-admin`)
- `tests/live/optional/test_live_reports_suite.py`: report lane (requires `--live-admin`)
- all live lanes are gated by `--run-live`
- live runtime defaults to sandbox (`--live-runtime sandbox`)
- prod live requires both `--allow-prod-live` and `TELECRAFT_ALLOW_PROD_LIVE=1`
- destructive operations require `--live-destructive`
- second-account lane additionally requires `--live-second-account <username>`
- paid steps additionally require `--live-paid`
- business lane additionally requires `--live-business`
- chatlists lane additionally requires `--live-chatlists`
- calls readonly lane additionally requires `--live-calls`
- calls write lane additionally requires `--live-calls-write`
- takeout lane additionally requires `--live-takeout`
- webapps lane additionally requires `--live-webapps`
- admin-sensitive lanes additionally require `--live-admin`
- stories write lane additionally requires `--live-stories-write`
- channel admin lane additionally requires `--live-channel-admin`
- audit trail is written to Telegram + local report files (`reports/live/<runtime>/<run_id>/`)

## Governance

- source of truth: `tests/meta/v2_method_matrix.yaml`
- each wrapper method must have a matrix row with stability + lane + required scenarios
- naming convention enforced: `test_<namespace>__<method>__<scenario>`
- compatibility policy: additive changes + explicit deprecation windows
