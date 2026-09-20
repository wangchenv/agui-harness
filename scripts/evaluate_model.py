#!/usr/bin/env python3
"""Run a reviewed project provider; --live explicitly opts into external model calls."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agui_eval.evidence import emit
from agui_eval.model import evaluate, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--prices', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--max-samples', type=int, default=100)
    parser.add_argument('--timeout-s', type=float, default=30)
    args = parser.parse_args()
    root = Path(os.environ.get('AGUI_PROJECT_ROOT', Path.cwd())).resolve()
    output = Path(os.environ.get('AGUI_ARTIFACT_DIR', root / '.agui/evidence/model-artifacts')) / uuid.uuid4().hex
    try:
        spec = importlib.util.spec_from_file_location('project_provider', args.provider.resolve())
        provider = importlib.util.module_from_spec(spec); spec.loader.exec_module(provider)
        result = evaluate(provider, args.dataset, model=args.model, prices=read_json(args.prices),
                          output_dir=output, root=root, baseline_path=args.baseline, live=args.live,
                          max_samples=args.max_samples, timeout_s=args.timeout_s)
    except Exception as exc:
        # Do not echo provider exception messages: they may contain credentials.
        result = {'schema_version': 1, 'cases': [
            {'id': 'task_quality', 'status': 'failed', 'detail': f'Evaluation could not complete: {type(exc).__name__}'},
            {'id': 'operator_efficiency', 'status': 'skipped', 'detail': 'Evaluation setup failed.'}]}
    return emit(result)


if __name__ == '__main__': raise SystemExit(main())
