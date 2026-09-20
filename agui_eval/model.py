"""Bounded exact-structure evaluation. A project adapter owns model API access.

Raw traces are evidence for review, not independent proof against a malicious
adapter. Human efficiency requires separately collected paired observations.
"""
import hashlib
import json
import math
from pathlib import Path
import time

from .evidence import artifact


def read_json(path):
    if Path(path).stat().st_size > 10 * 1024 * 1024:
        raise ValueError('evaluation input exceeds 10 MiB')
    return json.loads(Path(path).read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('non-finite JSON')))


def finite(value, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError('finite non-negative measurement required')
    return value


def efficiency(baseline, ids):
    if baseline.get('source_kind') != 'observed' or not all(baseline.get(k) for k in ('study_id', 'collected_at', 'population', 'baseline_version')):
        raise ValueError('observed study provenance required')
    rows = baseline['pairs']
    if len(rows) != len(ids) or {r['sample_id'] for r in rows} != set(ids):
        raise ValueError('baseline pairs must exactly match unique dataset samples')
    for row in rows:
        finite(row['baseline_seconds'], positive=True); finite(row['assisted_seconds'], positive=True)
        if type(row['baseline_rework']) is not bool or type(row['assisted_rework']) is not bool:
            raise ValueError('observed rework flags required')
    return {'human_time_reduction': 1 - sum(r['assisted_seconds'] for r in rows) / sum(r['baseline_seconds'] for r in rows),
            'rework_delta': sum(int(r['assisted_rework']) - int(r['baseline_rework']) for r in rows) / len(rows)}


def evaluate(provider, dataset_path, *, model, prices, output_dir, root, baseline_path=None,
             live=False, max_samples=100, timeout_s=30):
    dataset = read_json(dataset_path)
    samples = dataset['samples']
    if type(max_samples) is not int or not 1 <= max_samples <= 10000: raise ValueError('invalid sample budget')
    if not isinstance(samples, list) or not 0 < len(samples) <= max_samples:
        raise ValueError('empty dataset or sample budget exceeded')
    ids = [s['id'] for s in samples]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids): raise ValueError('unique sample IDs required')
    if not isinstance(dataset.get('dataset_id'), str) or not dataset['dataset_id']: raise ValueError('dataset ID required')
    if not all('input' in s and 'expected' in s for s in samples): raise ValueError('input and expected values required')
    if dataset.get('scoring') != 'structured_exact_match': raise ValueError('only structured_exact_match is supported')
    if not isinstance(model, str) or not model: raise ValueError('exact model version required')
    if prices.get('currency') != 'USD': raise ValueError('cost unit is USD')
    if prices.get('model_version') != model: raise ValueError('prices must name the exact model')
    input_price, output_price = finite(prices['input_per_million']), finite(prices['output_per_million'])
    finite(timeout_s, positive=True)
    required_mode = 'live_model' if live else 'offline'
    if getattr(provider, 'EXECUTION_MODE', None) != required_mode:
        raise ValueError('provider execution mode does not match explicit run mode')
    dataset_digest = hashlib.sha256(Path(dataset_path).read_bytes()).hexdigest()
    baseline = read_json(baseline_path) if baseline_path else None
    human_metrics, baseline_error = None, None
    if baseline:
        try:
            if baseline.get('model_version') != model or baseline.get('dataset_id') != dataset['dataset_id']:
                raise ValueError('baseline must match this model and dataset')
            if baseline.get('dataset_sha256') != dataset_digest:
                raise ValueError('baseline dataset content mismatch')
            human_metrics = efficiency(baseline, ids)
        except (ValueError, KeyError, TypeError): baseline_error = 'invalid or non-observed paired baseline'
    output_dir = Path(output_dir).resolve(); root = Path(root).resolve()
    output_dir.relative_to(root)
    output_dir.mkdir(parents=True, exist_ok=False)
    records, successes, costs, latencies = [], 0, 0.0, []
    trace = output_dir / 'samples.jsonl'
    # Raw input/output may contain personal data. Use authorized, non-sensitive datasets;
    # do not publish these traces by default in a public CI workflow.
    with trace.open('x') as stream:
        for sample in samples:
            started = time.monotonic()
            record = {'sample_id': sample['id'], 'input': sample['input'], 'expected': sample['expected']}
            try:
                prediction = provider.predict(sample['input'], model=model, timeout_s=timeout_s)
                if prediction['model_version'] != model or not isinstance(prediction['request_id'], str) or not prediction['request_id']:
                    raise ValueError('provider must return exact model and request ID')
                for key in ('input_tokens', 'output_tokens'):
                    if type(prediction[key]) is not int or prediction[key] < 0: raise ValueError('invalid token usage')
                encoded = json.dumps(prediction['output'], sort_keys=True, allow_nan=False)
                if len(encoded.encode()) > 65536: raise ValueError('output too large')
                passed = encoded == json.dumps(sample['expected'], sort_keys=True, allow_nan=False)
                cost = (prediction['input_tokens'] * input_price + prediction['output_tokens'] * output_price) / 1_000_000
                finite(cost)
                successes += int(passed); costs += cost
                record.update(status='passed' if passed else 'failed', prediction=prediction, cost_usd=cost)
            except Exception as exc:
                record.update(status='error', error_type=type(exc).__name__)
            record['latency_ms'] = (time.monotonic() - started) * 1000
            latencies.append(record['latency_ms']); records.append(record)
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n'); stream.flush()
    metrics = {'sample_size': len(samples), 'task_success_rate': successes / len(samples),
               'p95_latency_ms': sorted(latencies)[math.ceil(len(samples) * .95) - 1]}
    if successes: metrics['cost_per_success'] = costs / successes
    if human_metrics and live: metrics.update(human_metrics)
    # A quality case proves the experiment completed, not that its success rate meets
    # the release target. The harness compares the numeric metric to project policy.
    completed = all(r['status'] != 'error' for r in records) and successes > 0
    cases = [{'id': 'task_quality', 'status': ('passed' if completed else 'failed') if live else 'skipped',
              'detail': 'Live structured-output evaluation completed; inspect metrics and traces.' if live else 'Offline evaluator exercise; not live-model quality evidence.'},
             {'id': 'operator_efficiency', 'status': 'passed' if live and human_metrics else 'skipped',
              'detail': 'Matched observed task pairs; methodology still requires review.' if live and human_metrics else (baseline_error or 'Real paired human baseline unavailable or run is offline.')}]
    manifest = {'dataset_sha256': dataset_digest, 'model': model, 'execution_mode': required_mode,
                'prices': prices, 'metrics': metrics,
                'baseline_sha256': hashlib.sha256(Path(baseline_path).read_bytes()).hexdigest() if baseline_path else None,
                'provider_source_sha256': hashlib.sha256(Path(provider.__file__).read_bytes()).hexdigest()}
    manifest_path = output_dir / 'run.json'; manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False))
    context = {'execution_mode': 'live_model' if live else 'deterministic'}
    if live:
        context.update(model_version=model, dataset_id=dataset['dataset_id'],
                       baseline_version=baseline.get('baseline_version', 'missing') if baseline else 'missing')
    return {'schema_version': 1, 'cases': cases, 'context': context, 'metrics': metrics,
            'artifacts': [artifact(trace, root), artifact(manifest_path, root)]}
