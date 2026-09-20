#!/usr/bin/env python3
"""Local design/evidence harness. Passing is scoped evidence, never certification.

Adapters are trusted repository programs; inspect them before `run`. No shell is
used. Hashes detect accidental stale evidence, not a malicious repository owner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

try:
    from jsonschema import Draft202012Validator
except ImportError:
    raise SystemExit('Missing jsonschema. Install the plugin requirements.txt in your Python environment.')

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / 'scripts'))
import ui_audit
VERSION = '0.2.0'
CONTROL_NAMES = {
    'H01': '身份权限与租户隔离', 'H02': '业务操作幂等', 'H03': '提案版本与批准',
    'H04': '提交一致性与结果对账', 'H05': '会话并发与撤销', 'H06': 'UI 终态与业务凭证',
    'H07': '事实来源与新鲜度', 'H08': '记忆顺序与删除', 'H09': '时间并发费用预算',
    'H10': '用户意图与错误模型边界', 'H11': '真实任务质量与效率', 'H12': '观测与降级',
}
BASE_CASES = {
    'H01': ['tenant_isolation'], 'H02': ['duplicate_commit', 'changed_payload', 'concurrent_duplicate'],
    'H03': ['stale_proposal', 'unapproved_proposal'], 'H04': ['rollback_gap', 'lost_response'],
    'H05': ['session_conflict', 'session_revocation'], 'H06': ['partial_disconnect'],
    'H07': ['stale_evidence'], 'H08': ['memory_delete', 'memory_order'],
    'H09': ['tool_deadline', 'concurrency_budget'], 'H10': ['denied_intent', 'false_success'],
    'H11': ['task_quality', 'operator_efficiency'], 'H12': ['audit_trace', 'degraded_mode'],
}
IGNORE_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache'}
GENERATED = {'.agui/STATE.json', '.agui/HANDOFF.md'}


class HarnessError(Exception):
    pass


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (OSError, ValueError) as exc:
        raise HarnessError(f'Cannot read JSON {path}: {exc}') from exc


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value).encode()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.tmp-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def within(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise HarnessError(f'Project path must be relative and contained: {relative}')
    result = (root / path).resolve()
    if not result.is_relative_to(root):
        raise HarnessError(f'Path escapes project: {relative}')
    return result


def safe_output(root, relative):
    """Generated artifacts may never traverse symlinks, including inside root."""
    result = within(root, relative)
    cursor = root
    for part in Path(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise HarnessError(f'Generated/metadata paths cannot be symlinks: {relative}')
    return result


def validate_schema(value, name):
    schema = read_json(PLUGIN / 'schemas' / name)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: str(e.path))
    return [f'{".".join(map(str, e.path)) or "$"}: {e.message}' for e in errors]


def required_controls(contract):
    f = contract['features']
    result = {'H01', 'H07'}
    if f['writes']:
        result.update(['H02', 'H03', 'H04'])
    if f['sessions']:
        result.add('H05')
    if f['ui']:
        result.add('H06')
    if f['memory']:
        result.add('H08')
    if contract['project']['scope'] == 'application':
        result.update(['H09', 'H10', 'H11', 'H12'])
    return result


def required_cases(control, contract):
    result = list(BASE_CASES[control])
    if control == 'H01':
        result.append('unauthorized_write' if contract['features']['writes'] else 'unauthorized_read')
    if control == 'H06' and contract['features']['writes']:
        result.append('receipt_required')
    if control == 'H06' and contract.get('ui_design'):
        result.extend(['responsive_layout', 'keyboard_navigation', 'ui_state_recovery'])
    if control == 'H04' and contract['features']['external_writes']:
        result.extend(['unknown_outcome', 'reconciliation'])
    return result


def load_contract(root):
    contract = read_json(safe_output(root, '.agui/contract.json'))
    errors = validate_schema(contract, 'contract.schema.json')
    if errors:
        raise HarnessError('Invalid contract:\n' + '\n'.join(errors))
    return contract


def lint(root, contract, require_implementation=False):
    errors = []
    if contract['status'] != 'ready':
        errors.append('Contract is draft: resolve domain decisions before marking ready.')
    f = contract['features']
    if f['external_writes'] and not f['writes']:
        errors.append('external_writes requires writes.')
    if f['memory'] and not f['sessions']:
        errors.append('This profile requires sessions when memory is enabled.')
    paths = []
    ui = contract.get('ui_design')
    if f['ui'] and contract['project']['scope'] == 'application' and not ui:
        errors.append('UI applications require ui_design spec/tokens/inventory/prototype.')
    if ui:
        if not f['ui']:
            errors.append('ui_design requires features.ui.')
        for kind in ['spec','tokens','inventory']:
            paths.append(('ui_design.' + kind, ui[kind]))
        spec = within(root, ui['spec'])
        if spec.is_file() and spec.read_bytes() == (PLUGIN/'templates/ui-design.md').read_bytes():
            errors.append('UI design is an unchanged starter template.')
        for kind, validator in [('tokens', ui_audit.audit_tokens), ('inventory', ui_audit.audit_inventory)]:
            path = within(root, ui[kind])
            if path.is_file():
                errors.extend('ui_design.'+kind+': '+e for e in validator(read_json(path)))
        if require_implementation:
            paths.append(('ui_design.prototype', ui['prototype']))
    for label, value in contract['design'].items():
        paths.append((f'design.{label}', value))
        path = within(root, value)
        template = PLUGIN / 'templates' / (label + '.md')
        if path.is_file() and template.is_file() and path.read_bytes() == template.read_bytes():
            errors.append(f'design.{label}: unchanged starter template; complete project-specific decisions.')
    for value in contract['source_paths']:
        if require_implementation and not within(root, value).exists():
            errors.append(f'source_paths missing: {value}')
    tool_by_name = {t['name']: t for t in contract['tools']}
    if len(tool_by_name) != len(contract['tools']):
        errors.append('Duplicate tool names.')
    writes = {name for name, t in tool_by_name.items() if t['kind'] == 'write'}
    if bool(writes) != f['writes']:
        errors.append('features.writes must match declared write tools.')
    if bool(contract['components']) != f['ui']:
        errors.append('features.ui must match declared components.')
    for tool in contract['tools']:
        for kind in ['input_schema', 'output_schema']:
            paths.append((tool['name'] + '.' + kind, tool[kind]))
            path = within(root, tool[kind])
            if path.is_file():
                schema = read_json(path)
                try:
                    Draft202012Validator.check_schema(schema)
                except Exception as exc:
                    errors.append(f'{path}: invalid JSON Schema: {exc}')
                if not isinstance(schema, dict) or schema.get('type') != 'object' or schema.get('additionalProperties') is not False:
                    errors.append(f'{tool["name"]}.{kind}: root must be a closed object schema.')
        if tool['kind'] == 'write':
            if tool['risk'] == 'R0' or tool['idempotency'] != 'required' or tool['precondition'] not in {'entity_version', 'atomic_predicate'} or not tool['receipt']:
                errors.append(f'{tool["name"]}: write needs non-R0 risk, idempotency, atomic precondition and receipt.')
            if tool['precondition'] == 'atomic_predicate' and not tool.get('precondition_detail', '').strip():
                errors.append(f'{tool["name"]}: atomic_predicate needs precondition_detail naming the backend constraint and conflict behavior.')
            if tool['risk'] in {'R2', 'R3'} and tool['approval'] != 'explicit':
                errors.append(f'{tool["name"]}: R2/R3 needs explicit approval.')
            if tool['risk'] == 'R1' and tool['approval'] == 'none':
                errors.append(f'{tool["name"]}: R1 needs bounded policy or explicit approval.')
    covered_writes = set()
    workflow_ids = set()
    for flow in contract['workflows']:
        if flow['id'] in workflow_ids:
            errors.append(f'Duplicate workflow {flow["id"]}.')
        workflow_ids.add(flow['id'])
        states = set(flow['states'])
        if flow['initial'] not in states or not set(flow['terminals']) <= states:
            errors.append(f'{flow["id"]}: unknown initial/terminal state.')
        edges = flow['transitions']
        if any(e['from'] not in states or e['to'] not in states for e in edges):
            errors.append(f'{flow["id"]}: transition references unknown state.')
        if any(e['from'] in flow['terminals'] for e in edges):
            errors.append(f'{flow["id"]}: terminal states cannot transition; compensation is a new operation.')
        reachable = {flow['initial']}
        for _ in states:
            reachable |= {e['to'] for e in edges if e['from'] in reachable}
        if not states <= reachable:
            errors.append(f'{flow["id"]}: unreachable states {sorted(states - reachable)}.')
        can_finish = set(flow['terminals'])
        for _ in states:
            can_finish |= {e['from'] for e in edges if e['to'] in can_finish}
        if not states <= can_finish:
            errors.append(f'{flow["id"]}: states without a resolution path {sorted(states - can_finish)}.')
        if not set(flow['write_tools']) <= writes:
            errors.append(f'{flow["id"]}: unknown/non-write tool.')
        if flow['write_tools'] and not {'committed', 'failed', 'unknown'} <= states:
            errors.append(f'{flow["id"]}: write workflow must represent committed/failed/unknown.')
        if 'unknown' in flow['terminals']:
            errors.append(f'{flow["id"]}: unknown is unresolved, not a terminal success/failure.')
        covered_writes.update(flow['write_tools'])
    if writes - covered_writes:
        errors.append(f'Write tools without workflow: {sorted(writes - covered_writes)}')
    component_names = set()
    for component in contract['components']:
        if component['name'] in component_names:
            errors.append(f'Duplicate component {component["name"]}.')
        component_names.add(component['name'])
        paths.append((component['name'] + '.schema', component['schema']))
        if not set(component['action_tools']) <= writes:
            errors.append(f'{component["name"]}: action must reference a declared write tool.')
        if 'model' in component['critical_fields'].values():
            errors.append(f'{component["name"]}: critical facts cannot be model-authored.')
        path = within(root, component['schema'])
        if path.is_file():
            try:
                schema = read_json(path)
                Draft202012Validator.check_schema(schema)
                if not isinstance(schema, dict) or schema.get('type') != 'object' or schema.get('additionalProperties') is not False:
                    errors.append(f'{component["name"]}: component schema must be a closed object.')
                elif not set(component['critical_fields']) <= set(schema.get('properties', {})):
                    errors.append(f'{component["name"]}: critical_fields must name schema properties.')
            except Exception as exc:
                errors.append(f'{component["name"]}: invalid component schema: {exc}')
    checks = contract['checks']
    ids = [c['id'] for c in checks]
    if len(set(ids)) != len(ids):
        errors.append('Duplicate check ids.')
    cases = [case for c in checks for case in c['cases']]
    owners = {case: c for c in checks for case in c['cases']}
    if len(set(cases)) != len(cases):
        errors.append('A case must have exactly one check owner.')
    for check in checks:
        for relative in check['inputs']:
            path = within(root, relative)
            if require_implementation or path.exists():
                paths.append((check['id'] + '.inputs', relative))
            elif not any(path == within(root, p) or path.is_relative_to(within(root, p)) for p in contract['source_paths']):
                errors.append(f'{check["id"]}: planned input outside source_paths: {relative}')
        for arg in check['command']:
            if not arg.startswith('-') and Path(arg).suffix in {'.py', '.js', '.mjs', '.cjs', '.ts', '.sh'}:
                if arg not in check['inputs']:
                    errors.append(f'{check["id"]}: command script must be declared in inputs: {arg}')
    for control, value in contract['controls'].items():
        must = control in required_controls(contract)
        if must and value['applicability'] != 'required':
            errors.append(f'{control}: required by features/scope, cannot waive.')
        if value['applicability'] == 'required':
            if require_implementation and not value['implementation']:
                errors.append(f'{control}: missing implementation paths.')
            missing = set(required_cases(control, contract)) - set(value['cases'])
            if missing:
                errors.append(f'{control}: missing mandatory cases {sorted(missing)}.')
            if not set(value['cases']) <= set(cases):
                errors.append(f'{control}: cases have no check owner.')
            allowed = {'model_eval'} if control == 'H11' else {'deterministic', 'recovery'}
            if control == 'H06':
                allowed.add('ui')
            for case in value['cases']:
                if case in owners and owners[case]['kind'] not in allowed:
                    errors.append(f'{control}: case {case} must use check kind {sorted(allowed)}.')
                if case in {'responsive_layout','keyboard_navigation','ui_state_recovery'} and case in owners and owners[case]['kind'] != 'ui':
                    errors.append(f'{control}: browser case {case} requires a ui check.')
            if require_implementation:
                paths.extend((control + '.implementation', p) for p in value['implementation'])
        elif value['implementation'] or value['cases']:
            errors.append(f'{control}: not_applicable must not claim implementation/cases.')
    roots = [within(root, p) for p in contract['source_paths']]
    for label, relative in paths:
        path = within(root, relative)
        if not path.is_file() or not path.read_bytes().strip():
            errors.append(f'{label}: missing/empty file {relative}')
        if not any(path == p or path.is_relative_to(p) for p in roots):
            errors.append(f'{label}: {relative} is outside source_paths snapshot coverage.')
    # The contract and all declared design/schema files are included even if source_paths narrows scope.
    return errors


def snapshot(root, contract):
    files = {root / '.agui/contract.json'}
    for relative in contract['source_paths']:
        selected = within(root, relative)
        if not selected.exists():
            raise HarnessError(f'Snapshot input missing: {relative}')
        candidates = [selected] if selected.is_file() else selected.rglob('*')
        for candidate in candidates:
            rel = candidate.relative_to(root)
            if any(p in IGNORE_DIRS for p in rel.parts) or str(rel) in GENERATED or str(rel).startswith('.agui/evidence/'):
                continue
            if candidate.is_symlink():
                raise HarnessError(f'Snapshot inputs cannot be symlinks: {rel}')
            if candidate.is_file():
                files.add(candidate)
    if len(files) > 20000:
        raise HarnessError('Snapshot exceeds 20,000 files. Narrow source_paths to the reviewed component and its dependencies.')
    listing = {}
    total = 0
    for path in sorted(files):
        data = path.read_bytes()
        total += len(data)
        if total > 100 * 1024 * 1024:
            raise HarnessError('Snapshot exceeds 100 MiB. Narrow source_paths; do not include generated data.')
        listing[str(path.relative_to(root))] = sha(data)
    return {'hash': sha(listing), 'files': listing}


def engine_hash():
    paths = [Path(__file__).resolve(), PLUGIN/'scripts/ui_audit.py', PLUGIN/'schemas/ui-tokens.schema.json',
             PLUGIN/'schemas/ui-inventory.schema.json', PLUGIN/'schemas/contract.schema.json', PLUGIN/'schemas/result.schema.json']
    paths += [PLUGIN/'scripts/browser_probe.cjs', PLUGIN/'scripts/evaluate_model.py', PLUGIN/'package-lock.json']
    paths += sorted((PLUGIN/'agui_runtime').glob('*.py')) + sorted((PLUGIN/'agui_eval').glob('*.py'))
    return sha({str(p.relative_to(PLUGIN)): sha(p.read_bytes()) for p in paths})


def check_result(result, check):
    errors = validate_schema(result, 'result.schema.json')
    if errors:
        return errors
    cases = result['cases']
    ids = [case['id'] for case in cases]
    if len(set(ids)) != len(ids) or set(ids) != set(check['cases']):
        errors.append('Adapter must report exactly the declared unique case IDs, no missing/extra/duplicate cases.')
    if any(case['status'] != 'passed' for case in cases):
        errors.append('Failed or skipped cases cannot satisfy a gate.')
    if check['kind'] != 'deterministic':
        required_mode = {'model_eval':'live_model', 'load':'load', 'recovery':'recovery', 'ui':'browser'}[check['kind']]
        context = result.get('context', {})
        if context.get('execution_mode') != required_mode:
            errors.append(f'{check["kind"]} evidence requires context.execution_mode={required_mode}.')
        if check['kind'] == 'model_eval' and not all(context.get(k) for k in ['model_version','dataset_id','baseline_version']):
            errors.append('Live evaluation requires model_version, dataset_id and baseline_version.')
        if check['kind'] in {'model_eval', 'ui'} and not result.get('artifacts'):
            errors.append('Browser/live-model evidence requires retained raw artifacts.')
    return errors


def check_artifacts(root, result):
    errors, paths, size = [], set(), 0
    for item in (result or {}).get('artifacts', []):
        try:
            path = within(root, item['path'])
            if path in paths:
                errors.append('Duplicate artifact path: ' + item['path'])
            paths.add(path)
            if not path.is_file():
                errors.append('Missing artifact: ' + item['path'])
                continue
            size += path.stat().st_size
            if size > 100 * 1024 * 1024:
                errors.append('Artifacts exceed 100 MiB per check.')
                break
            if sha(path.read_bytes()) != item['sha256']:
                errors.append('Artifact digest mismatch: ' + item['path'])
        except (HarnessError, OSError, KeyError, TypeError) as exc:
            errors.append(f'Invalid artifact: {exc}')
    return errors


def run_check(root, contract, check):
    directory = safe_output(root, '.agui/evidence')
    directory.mkdir(parents=True, exist_ok=True)
    lock = safe_output(root, '.agui/evidence/' + check['id'] + '.lock')
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise HarnessError(f'Check already running or left an interrupted lock: {lock}. Confirm the owner stopped before removing it.') from exc
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump({'pid':os.getpid(), 'started_at':time.time()}, stream)
        return _run_check(root, contract, check)
    finally:
        lock.unlink(missing_ok=True)


def _run_check(root, contract, check):
    directory = safe_output(root, '.agui/evidence')
    directory.mkdir(parents=True, exist_ok=True)
    path = safe_output(root, '.agui/evidence/' + check['id'] + '.json')
    path.unlink(missing_ok=True)  # An interrupted/new failing run must not leave an older green result.
    before = snapshot(root, contract)
    before_engine = engine_hash()
    command = [sys.executable if arg == '{python}' else arg for arg in check['command']]
    start = time.time()
    errors = []
    result = None
    exit_code = None
    with tempfile.TemporaryDirectory(prefix='agui-result-') as temp:
        output_path = Path(temp) / 'result.json'
        artifact_dir = safe_output(root, '.agui/evidence/' + check['id'] + '-artifacts')
        env = dict(os.environ, AGUI_EVIDENCE_OUTPUT=str(output_path), AGUI_PROJECT_ROOT=str(root),
                   AGUI_ARTIFACT_DIR=str(artifact_dir))
        log_path = safe_output(root, '.agui/evidence/' + check['id'] + '.log')
        with log_path.open('wb') as log:
            try:
                process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                           shell=False, start_new_session=(os.name == 'posix'))
                try:
                    exit_code = process.wait(timeout=check['timeout_s'])
                except subprocess.TimeoutExpired:
                    if os.name == 'posix':
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait()
                    errors.append('Check timed out; on Windows descendant cleanup is adapter responsibility.')
            except OSError as exc:
                errors.append(f'Cannot execute adapter: {exc}')
        if exit_code != 0:
            errors.append(f'Adapter exit code: {exit_code}')
        if output_path.is_file() and output_path.stat().st_size <= 2 * 1024 * 1024:
            try:
                result = read_json(output_path)
                errors.extend(check_result(result, check))
                if not validate_schema(result, 'result.schema.json'):
                    errors.extend(check_artifacts(root, result))
            except HarnessError as exc:
                errors.append(str(exc))
        else:
            errors.append('Adapter did not produce a fresh result file of at most 2 MiB.')
    after = snapshot(root, contract)
    if before['hash'] != after['hash']:
        errors.append('Source changed while check ran. Review changes and rerun.')
    if before_engine != engine_hash():
        errors.append('Harness changed while check ran. Rerun with one fixed version.')
    receipt = {'schema_version':1, 'harness_version':VERSION, 'engine_hash':before_engine,
        'check_id':check['id'], 'command':check['command'], 'contract_hash':sha(contract),
        'source_hash':before['hash'], 'source_files':before['files'],
        'started_at':start, 'finished_at':time.time(), 'exit_code':exit_code,
        'environment':{'python':platform.python_version(), 'platform':platform.platform()},
        'status':'failed' if errors else 'passed', 'errors':errors, 'result':result}
    write_json(path, receipt)
    return receipt


def inspect_evidence(root, contract, check, current):
    path = safe_output(root, '.agui/evidence/' + check['id'] + '.json')
    if not path.is_file():
        return None, ['missing evidence']
    try:
        evidence = read_json(path)
        errors = []
        for key, expected in [('schema_version',1), ('engine_hash',engine_hash()), ('check_id',check['id']),
                              ('contract_hash',sha(contract)), ('source_hash',current['hash']), ('command',check['command'])]:
            if evidence.get(key) != expected:
                errors.append(f'stale/mismatched {key}')
        if evidence.get('status') != 'passed' or evidence.get('exit_code') != 0 or evidence.get('errors'):
            errors.append('check was not successful')
        finished = evidence.get('finished_at')
        if not isinstance(finished, (int, float)) or not 0 <= time.time() - finished <= contract['release']['evidence_max_age_hours'] * 3600:
            errors.append('evidence expired or timestamp invalid')
        errors.extend(check_result(evidence.get('result'), check))
        if not validate_schema(evidence.get('result'), 'result.schema.json'):
            errors.extend(check_artifacts(root, evidence['result']))
        return evidence, errors
    except (HarnessError, TypeError, AttributeError) as exc:
        return None, [f'invalid evidence: {exc}']


def gate(root, contract, stage):
    errors = lint(root, contract, require_implementation=(stage != 'design'))
    if errors:
        return {'status':'blocked','stage':stage,'errors':errors}
    if stage == 'design':
        return {'status':'passed','stage':stage,'scope':'contract consistency only; implementation unverified','errors':[]}
    current = snapshot(root, contract)
    relevant = [c for c in contract['checks'] if stage == 'release' or c['kind'] in {'deterministic','recovery','ui'}]
    evidence_by_check = {}
    available_cases = set()
    for check in relevant:
        evidence, issues = inspect_evidence(root, contract, check, current)
        if issues:
            errors.extend(f'{check["id"]}: {issue}' for issue in issues)
        else:
            evidence_by_check[check['id']] = evidence
            available_cases.update(check['cases'])
    for control, value in contract['controls'].items():
        if value['applicability'] == 'required' and (stage == 'release' or control != 'H11'):
            missing = set(value['cases']) - available_cases
            if missing:
                errors.append(f'{control}: no fresh passing evidence for {sorted(missing)}')
    if stage == 'release':
        if contract['project']['scope'] != 'application':
            errors.append('Reference/component examples cannot pass an application release gate.')
        kinds = {c['kind'] for c in relevant if c['id'] in evidence_by_check}
        if not {'deterministic','model_eval','load','recovery'} <= kinds:
            errors.append('Release needs deterministic, live model_eval, load and recovery evidence.')
        live = [e['result'] for c in relevant if c['kind']=='model_eval' and (e:=evidence_by_check.get(c['id']))]
        loads = [e['result'] for c in relevant if c['kind']=='load' and (e:=evidence_by_check.get(c['id']))]
        limits = contract['release']
        for result in live:
            context = result.get('context', {})
            for actual, declared in [('model_version', 'model_version'), ('dataset_id', 'dataset_id'), ('baseline_version', 'baseline')]:
                if context.get(actual) != limits[declared]:
                    errors.append(f'Live evaluation version mismatch: {actual}')
            metrics = result.get('metrics', {})
            conditions = {
                'sample_size': lambda v: v >= limits['minimum_samples'],
                'task_success_rate': lambda v: v >= limits['task_success_min'],
                'human_time_reduction': lambda v: v >= limits['human_time_reduction_min'],
                'rework_delta': lambda v: v <= limits['rework_delta_max'],
                'cost_per_success': lambda v: v <= limits['cost_per_success_max'],
            }
            for key, condition in conditions.items():
                if key not in metrics or not condition(metrics[key]):
                    errors.append(f'Model/efficiency metric missing or outside threshold: {key}')
        for result in loads:
            metrics = result.get('metrics', {})
            if metrics.get('sample_size', 0) < limits['minimum_samples'] or metrics.get('p95_latency_ms', float('inf')) > limits['p95_latency_ms_max']:
                errors.append('Load sample size or p95 latency outside threshold.')
    return {'status':'blocked' if errors else 'passed','stage':stage, 'project_scope':contract['project']['scope'],
            'scope':'declared tests on snapshotted files; not an independent security or production certification',
            'source_hash':current['hash'],'errors':errors}


def initialize(root, project_id, domain):
    path = safe_output(root, '.agui')
    if path.exists():
        raise HarnessError('.agui already exists; init never overwrites existing work.')
    contract = read_json(PLUGIN / 'templates/contract.json')
    contract['project'].update(id=project_id, domain=domain)
    validation = validate_schema(contract, 'contract.schema.json')
    if validation:
        raise HarnessError('\n'.join(validation))
    path.mkdir(parents=True)
    for name in ['architecture','data','workflows','interaction','operations','evaluation']:
        target = path / 'design' / (name + '.md')
        target.parent.mkdir(exist_ok=True)
        target.write_text((PLUGIN/'templates'/f'{name}.md').read_text(), encoding='utf-8')
    (path / 'schemas').mkdir()
    for source in (PLUGIN / 'templates/schemas').glob('*.json'):
        (path / 'schemas' / source.name).write_text(source.read_text(), encoding='utf-8')
    (path / 'design/DESIGN.md').write_text((PLUGIN / 'templates/ui-design.md').read_text(), encoding='utf-8')
    for name in ['tokens.json','component-inventory.json']:
        (path / name).write_text((PLUGIN / 'templates' / name).read_text(), encoding='utf-8')
    write_json(path / 'contract.json', contract)
    write_json(path / 'STATE.json', {'schema_version':1,'phase':'design','objective':domain,'decisions':[],
                                   'open_questions':[],'next_action':'Complete design and contract; no implementation evidence exists.'})
    return {'status':'initialized','contract':str(path/'contract.json'),'next':'Read the design skill; resolve draft contract. No gate has passed.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('--id', default='new-application')
    init.add_argument('--domain', default='待明确的业务范围')
    commands.add_parser('lint')
    run = commands.add_parser('run')
    run.add_argument('--check', default='all')
    run.add_argument('--include-live', action='store_true', help='Also run declared model/load checks; requires existing authorization and configured test endpoints.')
    gating = commands.add_parser('gate')
    gating.add_argument('--stage', choices=['design','implementation','release'], default='implementation')
    commands.add_parser('status')
    commands.add_parser('handoff')
    args = parser.parse_args(argv)
    root = args.project.expanduser().resolve()
    try:
        if args.command == 'init':
            result = initialize(root, args.id, args.domain)
        else:
            contract = load_contract(root)
            if args.command == 'lint':
                errors = lint(root, contract)
                result = {'status':'blocked' if errors else 'passed','errors':errors,'scope':'declaration consistency only'}
            elif args.command == 'run':
                errors = lint(root, contract, require_implementation=True)
                if errors:
                    raise HarnessError('\n'.join(errors))
                selected = [c for c in contract['checks'] if args.check in {'all', c['id']}]
                if not selected:
                    raise HarnessError('Unknown check ID.')
                if not args.include_live:
                    if args.check != 'all' and any(c['kind'] in {'model_eval','load'} for c in selected):
                        raise HarnessError('Explicit live/load run needs --include-live; confirm authorization and inspect adapter first.')
                    selected = [c for c in selected if c['kind'] not in {'model_eval','load'}]
                if not selected:
                    raise HarnessError('No checks selected.')
                outcomes = [run_check(root, contract, check) for check in selected]
                result = {'status':'passed' if all(e['status']=='passed' for e in outcomes) else 'blocked',
                          'checks':[{'id':e['check_id'],'status':e['status'],'errors':e['errors']} for e in outcomes]}
            elif args.command == 'gate':
                result = gate(root, contract, args.stage)
            else:
                result = {'status':'reported','project':contract['project'],
                          'design':gate(root, contract, 'design'), 'implementation':gate(root, contract, 'implementation'),
                          'release':gate(root, contract, 'release')}
                if args.command == 'handoff':
                    target = safe_output(root, '.agui/HANDOFF.md')
                    target.write_text('# AGUI handoff\n\nGenerated UTC: '+datetime.now(timezone.utc).isoformat()+
                        '\n\nRead contract.json, STATE.json and the actual source. Rerun status before trusting this snapshot.\n\n```json\n'+
                        json.dumps(result,ensure_ascii=False,indent=2)+'\n```\n',encoding='utf-8')
                    result['handoff'] = str(target)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 1 if result.get('status') == 'blocked' else 0
    except (HarnessError, OSError, ValueError) as exc:
        print(json.dumps({'status':'blocked','errors':[str(exc)]},ensure_ascii=False,indent=2))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
