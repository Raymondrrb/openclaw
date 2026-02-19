# Quality Contracts (Originality + Compliance)

This project enforces two automatic contracts before Gate 2:

- `/Users/ray/Documents/Rayviews/rayvault/originality_validator.py`
- `/Users/ray/Documents/Rayviews/rayvault/compliance_contract.py`

## 1) Originality Budget thresholds

Defaults are defined in `DEFAULT_POLICY` inside `/Users/ray/Documents/Rayviews/rayvault/originality_validator.py`.

Key knobs:

- `min_script_uniqueness_score_ok` (default `0.72`)
- `min_script_uniqueness_score_fail` (default `0.58`)
- `max_template_phrase_hits_ok` (default `6`)
- `max_template_phrase_hits_fail` (default `12`)
- `min_products_with_evidence_ok` (default `5`)
- `min_products_with_evidence_fail` (default `4`)
- `min_opinion_density_ok` (default `0.12`)
- `min_opinion_density_fail` (default `0.08`)

Override per run:

```bash
python3 tools/pipeline.py validate-originality \
  --run-id RUN_ID \
  --policy-json '{"min_script_uniqueness_score_ok":0.78}'
```

## 2) Compliance Contract checks

`/Users/ray/Documents/Rayviews/rayvault/compliance_contract.py` enforces:

- intro disclosure in script opener (affiliate + commission mention),
- disclosure artifacts for description + pinned comment,
- no external shorteners for affiliate links (first-party `amzn.to` allowed),
- Amazon destination clarity in affiliate URLs.

Outputs:

- `compliance_report.json`
- `upload/disclosure_snippets.json`
- `upload/pinned_comment.txt`

## 3) Gate behavior

- Any `FAIL` in originality/compliance blocks Gate 2 approval.
- `WARN` requires explicit reviewer acknowledgement:

```bash
python3 tools/pipeline.py approve-gate2 --run-id RUN_ID --reviewer Ray --notes "#override-warn GO"
```
