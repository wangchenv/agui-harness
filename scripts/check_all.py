#!/usr/bin/env python3
"""Reproducible local/CI checks. Expected negative failures are inspected, not ignored."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
import harness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    output = ROOT / '.agui/evidence/ci'; output.mkdir(parents=True, exist_ok=True)
    records = []

    def run(name, command, expected=0, predicate=None, env=None):
        try:
            result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, **(env or {})), capture_output=True, text=True, timeout=180)
            (output / (name + '.log')).write_text(result.stdout + '\n' + result.stderr)
            valid = result.returncode == expected and (predicate is None or predicate(result))
            records.append({'id':name,'status':'passed' if valid else 'failed','exit_code':result.returncode})
        except Exception as exc:
            records.append({'id':name,'status':'failed','error_type':type(exc).__name__})

    def cases(result): return json.loads(result.stdout)['cases']
    py = sys.executable
    if args.browser:
        command = [os.environ.get('AGUI_NODE', 'node'), 'scripts/browser_probe.cjs', '--suite', 'examples/ui-workbench/browser.cjs']
        def browser_ok(result):
            report = json.loads(result.stdout)
            check = {'kind':'ui','cases':['responsive_layout','keyboard_navigation','ui_state_recovery']}
            return not harness.check_result(report,check) and not harness.check_artifacts(ROOT,report)
        run('browser',command,predicate=browser_ok)
        run('browser-negative',command+['--inject-defect'],expected=1,
            predicate=lambda r: [c['id'] for c in cases(r) if c['status']=='failed'] == ['ui_state_recovery'])
    else:
        run('unit',[py,'-m','unittest','discover','-s','tests','-q'])
        run('service-baseline',[py,'examples/service-desk/adapter.py'],
            predicate=lambda r: len(cases(r))==14 and all(c['status']=='passed' for c in cases(r)))
        for defect, required in [('skip_idempotency_replay','duplicate_commit'),('allow_unreceipted_commit','receipt_required')]:
            run('negative-'+defect,[py,'examples/service-desk/adapter.py','--inject-defect',defect],expected=1,
                predicate=lambda r, case=required: any(c['id']==case and c['status']=='failed' for c in cases(r)))
        run('runtime-negative',[py,'-m','unittest','discover','-s','tests','-p','test_runtime_domains.py','-q'],expected=1,
            env={'AGUI_TEST_DEFECT':'allow_overlap'},
            predicate=lambda r: 'FAIL: test_parallel_overlap_rejected_but_adjacent_allowed' in r.stderr and 'ERROR:' not in r.stderr)
        for stage, expected in [('design',0),('implementation',0),('release',1)]:
            if stage=='implementation':
                run('service-run',[py,'scripts/harness.py','--project','examples/service-desk','run'])
            run('service-'+stage,[py,'scripts/harness.py','--project','examples/service-desk','gate','--stage',stage],expected=expected,
                predicate=lambda r, value=expected: json.loads(r.stdout)['status']==('blocked' if value else 'passed'))
        run('equipment-design',[py,'scripts/harness.py','--project','examples/equipment-booking-design','gate','--stage','design'])
        run('ui-state',[os.environ.get('AGUI_NODE','node'),'examples/ui-workbench/test-state.cjs'])
        run('offline-model',[py,'scripts/evaluate_model.py','--provider','examples/model-evaluation/offline_provider.py',
            '--dataset','examples/model-evaluation/dataset.json','--prices','examples/model-evaluation/prices.json','--model','offline-fixture'],expected=1,
            predicate=lambda r: all(c['status']=='skipped' for c in cases(r)) and json.loads(r.stdout)['context']['execution_mode']=='deterministic')
    report={'scope':'toolkit checks; synthetic examples are not live-model/application release evidence','checks':records}
    (output / ('browser.json' if args.browser else 'core.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if records and all(r['status']=='passed' for r in records) else 1


if __name__ == '__main__': raise SystemExit(main())
