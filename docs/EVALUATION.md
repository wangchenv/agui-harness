# Reproducible browser and model evaluation

Version 0.2 adds actual runners and retained artifacts. A runner is not a universal business oracle: projects provide task-specific assertions, providers and human baselines. All imported suites/adapters are trusted executable code.

## Browser

From the plugin root:

```sh
npm ci --ignore-scripts
npx --no-install playwright install chromium
node scripts/browser_probe.cjs --suite examples/ui-workbench/browser.cjs
node scripts/browser_probe.cjs --suite examples/ui-workbench/browser.cjs --inject-defect
```

The first command run should pass three real browser cases. The negative run must fail `ui_state_recovery`: the actual page renderer is altered to expose an unsafe review button after interruption. The original assertion detects it. This prototype uses simulated in-page business data; these browser results do not prove backend transactions or model quality.

The runner saves a trace ZIP and screenshot per case, plus browser/Playwright versions and results. `--suite` loads a project module exporting `{url, cases: [{id, run}]}`; each function receives `{page, context, url, defect}`. `--url` overrides the target. Node 20+ is required. `AGUI_BROWSER_EXECUTABLE` optionally selects an existing browser for local checks; CI installs Playwright's pinned Chromium.

To integrate with a target's Harness, copy the runner and write a target-specific suite. Declare both scripts, the lockfile, assertions and relevant application code in `inputs`/`source_paths`. Register the check as `kind=ui` with the three case IDs. The runner writes the required result to `AGUI_EVIDENCE_OUTPUT` and raw files under `AGUI_ARTIFACT_DIR`. Give the whole check a timeout in the contract.

Browser automation does not measure aesthetic quality, actual screen-reader usability, touch keyboards, or user efficiency. The recorded trace supports review; visual review and representative user testing remain separate activities.

## Structured-output model evaluation

The first implementation deliberately supports `structured_exact_match`, not arbitrary free-text quality or an uncalibrated LLM judge.

```sh
python scripts/evaluate_model.py \
  --provider examples/model-evaluation/offline_provider.py \
  --dataset examples/model-evaluation/dataset.json \
  --prices examples/model-evaluation/prices.json \
  --model offline-fixture
```

This synthetic example must exit **1**, report `execution_mode=deterministic`, and mark both `task_quality` and `operator_efficiency` skipped. Its zero prices describe a free offline fixture, not any vendor's pricing.

For an authorized live run, supply a reviewed provider with `EXECUTION_MODE = "live_model"` and explicitly add `--live`. The provider implements:

```python
def predict(value, *, model, timeout_s):
    # Make one bounded provider request here. Credentials remain in the host.
    return {
        "output": parsed_structured_output,
        "model_version": exact_response_model,
        "request_id": provider_request_id,
        "input_tokens": actual_input_tokens,
        "output_tokens": actual_output_tokens,
    }
```

The evaluator has a sample budget, passes a timeout to the provider, validates model/usage metadata, counts failed calls in the denominator, computes USD cost per successful sample from supplied per-million-token prices, and retains one record per attempted sample. The price file must name the exact `model_version`; JSON inputs are limited to 10 MiB each. The provider must enforce its network timeout; Harness/CI must bound the whole process. Automatic retries, pricing lookup, monetary hard caps, and provider authentication are not implemented by this runner.

The dataset contains `dataset_id`, `scoring: "structured_exact_match"`, and unique `{id,input,expected}` samples. A quality case passes when the experiment completes with valid responses and at least one success; **the release gate separately checks the numeric success-rate target**. A passing case does not mean every prediction is correct.

### Human baseline

`--baseline` requires a separately collected JSON study with:

- `source_kind: "observed"`, `study_id`, `collected_at`, `population`, `baseline_version`;
- the exact `model_version`, `dataset_id`, and `dataset_sha256` evaluated;
- `pairs`, exactly one per sample ID, containing `sample_id`, positive `baseline_seconds`/`assisted_seconds`, and Boolean `baseline_rework`/`assisted_rework`.

Time reduction is `1 - total_assisted_seconds / total_baseline_seconds`; rework delta is the difference in observed rework proportions. Include review, correction and handoff time in the study. Matching IDs/provenance is mechanically checked, but representativeness, measurement quality and statistical uncertainty require human review. Missing, mismatched or synthetic baseline data cannot satisfy the efficiency case. This package supplies **no fabricated observed baseline**.

### Raw evidence and trust

`samples.jsonl` retains input, expected output, response, usage, request ID, latency and status. `run.json` records dataset/provider/baseline digests, model, pricing and metrics. Use authorized, non-sensitive evaluation data. Traces may contain private business text; do not upload live traces to public CI by default. Offline repository fixtures contain only synthetic data.

The result's `artifacts` lists project-relative paths and SHA-256 digests. Harness validates them after the run and again at each gate. From 0.2 onward, `ui` and `model_eval` checks require nonempty artifacts; existing adapters must migrate and regenerate evidence. Adapter labels and hashes still cannot prove authenticity against an owner who can rewrite every input, adapter and artifact.

Official API references used: [Playwright traces](https://playwright.dev/docs/trace-viewer) and [screenshots](https://playwright.dev/docs/screenshots).
