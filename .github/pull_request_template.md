## Summary
- What changed?
- Why now?

## V2 Matrix Checklist (Required)
- [ ] Added/updated rows in `tests/meta/v2_method_matrix.yaml` for every new/changed wrapper method
- [ ] Chosen `stability` (`experimental` or `stable`) for each method
- [ ] Chosen `tier` (`unit`, `manual_live_optional`, `external_manual`, or `unsupported_or_experimental`) for each method
- [ ] Filled `required_scenarios`, `introduced_in`, and `deprecation_target`
- [ ] Added tests using naming rule: `test_<namespace>__<method>__<scenario>`

## Scenario Coverage
- [ ] `delegates_to_raw`
- [ ] `forwards_args`
- [ ] `handles_rpc_error`
- [ ] `passes_timeout` (if method exposes timeout)
- [ ] `returns_expected_shape` (for stable wrappers)
- [ ] Manual validation notes recorded when tier is not `unit`

## Compatibility
- [ ] Change is additive OR has documented deprecation path
- [ ] No immediate API break without deprecation window

## Live Validation (if applicable)
- [ ] Ran prod-safe live smoke manually, if required for the change
- [ ] Attached run artifacts: `events.jsonl`, `summary.md`, `artifacts.json`
