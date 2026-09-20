"""Offline regression tests for fail-closed local evidence handling.

Adapters here deliberately return scripted results: tests verify harness behavior,
not model quality or application readiness. All projects and outputs use temp dirs.
Run: python -m unittest discover -s plugins/agui-harness/tests -p test_harness.py -v
"""

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agui_harness_under_test", PLUGIN / "scripts/harness.py")
H = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(H)

ADAPTER = '''import json, os, sys, time
from pathlib import Path
import helper
contract = json.loads(Path('.agui/contract.json').read_text())
check = next(c for c in contract['checks'] if c['id'] == sys.argv[1])
data = json.loads(Path('src/test-data.json').read_text())
mode = data.get('mode', 'ok')
if mode == 'sleep': time.sleep(10)
if mode == 'fail': raise SystemExit(7)
if mode == 'no_output': raise SystemExit(0)
output = Path(os.environ['AGUI_EVIDENCE_OUTPUT'])
if mode == 'malformed':
    output.write_text('{"schema_version":1,"cases":null}')
    raise SystemExit(0)
if mode == 'invalid_json':
    output.write_text('{broken json')
    raise SystemExit(0)
result = {'schema_version': 1, 'cases': [
    {'id': case, 'status': data.get('case_status', 'passed'), 'detail': helper.detail()}
    for case in check['cases']]}
if mode == 'missing_case': result['cases'].pop()
if mode == 'extra_case': result['cases'].append({'id':'unexpected_case','status':'passed','detail':'extra'})
if mode == 'duplicate_case': result['cases'].append(dict(result['cases'][0]))
kind = check['kind']
result['context'] = {'execution_mode': {
    'deterministic':'deterministic','model_eval':'live_model','load':'load','recovery':'recovery'}[kind]}
if kind == 'model_eval':
    result['context'].update({k:contract['release'][k if k != 'baseline_version' else 'baseline']
                             for k in ['model_version','dataset_id','baseline_version']})
    result['context'].update(data.get('live_context', {}))
    result['metrics'] = {'sample_size':10,'task_success_rate':1.0,'human_time_reduction':0.5,
                         'rework_delta':0.0,'cost_per_success':0.1}
    result['metrics'].update(data.get('live_metrics', {}))
if kind == 'load': result['metrics'] = {'sample_size':10,'p95_latency_ms':10}
output.write_text(json.dumps(result))
'''


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class HarnessTests(unittest.TestCase):
    def test_cli_runs_from_target_with_parent_relative_plugin_path(self):
        # The documented cross-project invocation can leave .. segments in
        # __file__. Evidence engine hashing must canonicalize before relative_to.
        entry = os.path.relpath(PLUGIN / 'scripts/harness.py', self.root)
        completed = subprocess.run(
            [sys.executable, entry, '--project', '.', 'run'],
            cwd=self.root, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['status'], 'passed')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agui-harness-regression-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project"
        self.contract = self.make_project(self.root)

    def make_project(self, root, scope="reference"):
        (root / "src").mkdir(parents=True)
        (root / "src/app.py").write_text("def read(): return 1\n")
        (root / "src/helper.py").write_text("def detail(): return 'offline harness fixture'\n")
        (root / "src/adapter.py").write_text(ADAPTER)
        write_json(root / "src/test-data.json", {})
        write_json(root / "src/schema.json", {
            "type":"object", "properties":{}, "additionalProperties":False,
        })
        design = {k:f"design/{k}.md" for k in (
            "architecture", "data", "workflows", "interaction", "operations", "evaluation")}
        for label, relative in design.items():
            path = root / relative
            path.parent.mkdir(exist_ok=True)
            path.write_text(f"# {label}\nA reviewed decision for this isolated harness fixture.\n")
        contract = {
            "schema_version":1, "status":"ready",
            "project":{"id":"fixture", "domain":"isolated read-only test", "scope":scope},
            "source_paths":["src", "design"],
            "features":dict(writes=False, sessions=False, memory=False, ui=False, external_writes=False),
            "design":design,
            "entities":[dict(name="item", authority="backend", id_field="id", tenant_field="tenant",
                             version_field="version", freshness="reread on use")],
            "tools":[dict(name="read_item", kind="read", input_schema="src/schema.json",
                          output_schema="src/schema.json", permission="read", identity_source="host",
                          risk="R0", timeout_ms=10, max_concurrency=1, idempotency="none",
                          approval="none", precondition="none", receipt=False)],
            "workflows":[dict(id="read", initial="start", states=["start", "done"], terminals=["done"],
                              transitions=[{"from":"start", "to":"done", "guard":"read complete"}],
                              write_tools=[], unknown_resolution="not applicable to pure read")],
            "components":[],
            "budgets":dict(turn_timeout_ms=100, max_tool_calls=5, max_parallel_tools=2,
                           max_input_bytes=1024, max_output_tokens=100, max_cost_microunits=100),
            "controls":{}, "checks":[],
            "release":dict(minimum_samples=5, task_success_min=.8, human_time_reduction_min=.1,
                           rework_delta_max=0, p95_latency_ms_max=1000, cost_per_success_max=2,
                           evidence_max_age_hours=24, baseline="baseline-v1",
                           model_version="model-v1", dataset_id="dataset-v1"),
        }
        required = H.required_controls(contract)
        deterministic, quality = [], []
        for control in H.CONTROL_NAMES:
            needed = control in required
            cases = H.required_cases(control, contract) if needed else []
            (quality if control == "H11" else deterministic).extend(cases)
            contract["controls"][control] = dict(
                applicability="required" if needed else "not_applicable",
                reason="covered by fixture" if needed else "outside this reference scope",
                implementation=["src/app.py"] if needed else [], cases=cases,
            )
        def check(kind, cases):
            return dict(id=kind, kind=kind, command=["{python}", "src/adapter.py", kind],
                        inputs=["src/adapter.py", "src/helper.py", "src/test-data.json"],
                        timeout_s=1, cases=cases)
        contract["checks"] = [check("deterministic", deterministic)]
        if scope == "application":
            contract["checks"] += [check("model_eval", quality), check("load", ["load_probe"]),
                                    check("recovery", ["recover_probe"])]
        write_json(root / ".agui/contract.json", contract)
        return contract

    def save(self):
        write_json(self.root / ".agui/contract.json", self.contract)

    def as_application(self):
        self.root = self.base / "application"
        self.contract = self.make_project(self.root, "application")

    def data(self, **values):
        write_json(self.root / "src/test-data.json", values)

    def run_all(self):
        errors = H.validate_schema(self.contract, "contract.schema.json")
        self.assertEqual(errors, [])
        self.assertEqual(H.lint(self.root, self.contract, require_implementation=True), [])
        return [H.run_check(self.root, self.contract, check) for check in self.contract["checks"]]

    def assert_gate(self, stage, status):
        result = H.gate(self.root, self.contract, stage)
        self.assertEqual(result["status"], status, result)
        return result

    def assert_rejected(self, callback):
        try:
            result = callback()
        except (H.HarnessError, OSError):
            return
        self.assertNotEqual(result.get("status"), "passed", result)

    def test_current_reference_evidence_passes_implementation_but_not_release(self):
        self.assertTrue(all(r["status"] == "passed" for r in self.run_all()))
        self.assert_gate("implementation", "passed")
        self.assert_gate("release", "blocked")

    def test_application_with_matching_live_versions_passes_release(self):
        self.as_application()
        self.assertTrue(all(r["status"] == "passed" for r in self.run_all()))
        self.assert_gate("release", "passed")

    def test_missing_evidence_does_not_pass(self):
        self.assert_gate("implementation", "blocked")

    def test_source_changes_invalidate_evidence(self):
        self.run_all()
        (self.root / "src/app.py").write_text("def read(): return 2\n")
        self.assert_gate("implementation", "blocked")

    def test_adapter_changes_invalidate_evidence(self):
        self.run_all()
        (self.root / "src/adapter.py").write_text("raise RuntimeError('newly broken adapter')\n")
        self.assert_gate("implementation", "blocked")

    def test_adapter_dependency_changes_invalidate_evidence(self):
        self.run_all()
        (self.root / "src/helper.py").write_text("def detail(): raise RuntimeError('broken helper')\n")
        self.assert_gate("implementation", "blocked")

    def test_missing_inputs_array_is_invalid_contract(self):
        self.contract["checks"][0].pop("inputs")
        self.assertTrue(H.validate_schema(self.contract, "contract.schema.json"))

    def test_command_script_must_be_explicit_input(self):
        self.contract["checks"][0]["inputs"].remove("src/adapter.py")
        self.assertTrue(H.lint(self.root, self.contract))

    def test_check_input_must_be_inside_source_snapshot(self):
        (self.root / "outside_snapshot.py").write_text("VALUE=1\n")
        self.contract["checks"][0]["inputs"].append("outside_snapshot.py")
        self.assertTrue(H.lint(self.root, self.contract))

    def test_missing_declared_input_is_rejected(self):
        self.contract["checks"][0]["inputs"].append("src/missing.py")
        self.assertEqual(H.lint(self.root, self.contract), [])
        self.assertTrue(H.lint(self.root, self.contract, require_implementation=True))
        self.assert_gate("implementation", "blocked")

    def test_h11_cases_cannot_be_owned_by_deterministic_check(self):
        self.as_application()
        deterministic, live = self.contract["checks"][:2]
        deterministic["cases"] += live["cases"]
        live["cases"] = ["unrelated_live_probe"]
        self.assertTrue(H.lint(self.root, self.contract))
        self.assert_gate("release", "blocked")

    def test_hard_control_cases_cannot_be_owned_by_live_check(self):
        self.as_application()
        deterministic, live = self.contract["checks"][:2]
        case = self.contract["controls"]["H01"]["cases"][0]
        deterministic["cases"].remove(case)
        live["cases"].append(case)
        self.assertTrue(H.lint(self.root, self.contract))

    def test_hard_controls_may_use_recovery_evidence(self):
        self.as_application()
        deterministic, _, _, recovery = self.contract["checks"]
        case = self.contract["controls"]["H01"]["cases"][0]
        deterministic["cases"].remove(case)
        recovery["cases"].append(case)
        self.save()
        self.assertTrue(all(r["status"] == "passed" for r in self.run_all()))
        self.assert_gate("release", "passed")

    def test_live_baseline_dataset_and_model_versions_must_match(self):
        self.as_application()
        for field in ("baseline_version", "dataset_id", "model_version"):
            with self.subTest(field=field):
                self.data(live_context={field:"different-version"})
                self.run_all()
                self.assert_gate("release", "blocked")

    def test_scripted_model_context_cannot_satisfy_live_evidence(self):
        self.as_application()
        self.data(live_context={"execution_mode":"deterministic"})
        receipts = self.run_all()
        self.assertEqual(next(r for r in receipts if r["check_id"] == "model_eval")["status"], "failed")
        self.assert_gate("release", "blocked")

    def test_metrics_reject_percentage_unit_mistake_and_invalid_rate_delta(self):
        base = {"schema_version":1, "cases":[{"id":"test", "status":"passed", "detail":"measured"}]}
        for metrics in ({"human_time_reduction":50}, {"rework_delta":1.1}, {"rework_delta":-1.1}):
            with self.subTest(metrics=metrics):
                self.assertTrue(H.validate_schema(dict(base, metrics=metrics), "result.schema.json"))

    def test_expired_or_future_evidence_does_not_pass(self):
        self.run_all()
        path = self.root / ".agui/evidence/deterministic.json"
        original = json.loads(path.read_text())
        for timestamp in (time.time()-25*3600, time.time()+3600):
            with self.subTest(timestamp=timestamp):
                modified = dict(original, finished_at=timestamp)
                write_json(path, modified)
                self.assert_gate("implementation", "blocked")

    def test_raw_adapter_result_cannot_impersonate_harness_receipt(self):
        receipt = self.run_all()[0]
        write_json(self.root / ".agui/evidence/deterministic.json", receipt["result"])
        self.assert_gate("implementation", "blocked")

    def test_failed_rerun_replaces_previous_green_receipt(self):
        self.run_all()
        self.data(mode="fail")
        receipt = H.run_check(self.root, self.contract, self.contract["checks"][0])
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["exit_code"], 7)
        saved = json.loads((self.root / ".agui/evidence/deterministic.json").read_text())
        self.assertEqual(saved["status"], "failed")
        self.assert_gate("implementation", "blocked")

    def test_malformed_missing_and_invalid_json_results_fail_closed(self):
        for mode in ("malformed", "no_output", "invalid_json"):
            with self.subTest(mode=mode):
                self.data(mode=mode)
                receipt = H.run_check(self.root, self.contract, self.contract["checks"][0])
                self.assertEqual(receipt["status"], "failed")
                self.assert_gate("implementation", "blocked")

    def test_missing_extra_duplicate_failed_or_skipped_cases_fail_closed(self):
        configs = [{"mode":m} for m in ("missing_case", "extra_case", "duplicate_case")]
        configs += [{"case_status":s} for s in ("failed", "skipped")]
        for values in configs:
            with self.subTest(values=values):
                self.data(**values)
                receipt = H.run_check(self.root, self.contract, self.contract["checks"][0])
                self.assertEqual(receipt["status"], "failed")
                self.assert_gate("implementation", "blocked")

    def test_timeout_fails_closed_and_does_not_reuse_older_receipt(self):
        self.run_all()
        self.data(mode="sleep")
        started = time.monotonic()
        receipt = H.run_check(self.root, self.contract, self.contract["checks"][0])
        self.assertLess(time.monotonic()-started, 5)
        self.assertEqual(receipt["status"], "failed")
        self.assertTrue(any("timed out" in error.lower() for error in receipt["errors"]))
        self.assert_gate("implementation", "blocked")

    def test_evidence_symlink_rejected_without_touching_external_files(self):
        outside = self.base / "external"
        outside.mkdir()
        sentinel = outside / "deterministic.json"
        sentinel.write_text("outside receipt must remain untouched")
        log = outside / "deterministic.log"
        log.write_text("outside log must remain untouched")
        try:
            (self.root / ".agui/evidence").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        self.assert_rejected(lambda: H.run_check(self.root, self.contract, self.contract["checks"][0]))
        self.assertEqual(sentinel.read_text(), "outside receipt must remain untouched")
        self.assertEqual(log.read_text(), "outside log must remain untouched")

    def test_source_path_traversal_rejected(self):
        for path in ("../outside", str(self.base / "outside")):
            with self.subTest(path=path):
                with self.assertRaises(H.HarnessError):
                    H.within(self.root, path)

    def test_unmodified_design_templates_cannot_be_marked_ready(self):
        for label, relative in self.contract["design"].items():
            (self.root / relative).write_bytes((PLUGIN / "templates" / (label + ".md")).read_bytes())
        self.assert_gate("design", "blocked")

    def test_draft_contract_cannot_pass_design(self):
        self.contract["status"] = "draft"
        self.assert_gate("design", "blocked")

    def test_existing_run_lock_preserves_old_evidence_and_lock(self):
        self.run_all()
        receipt = self.root / '.agui/evidence/deterministic.json'
        original = receipt.read_bytes()
        lock = self.root / '.agui/evidence/deterministic.lock'
        lock.write_text('another runner owns this check')
        with self.assertRaises(H.HarnessError):
            H.run_check(self.root, self.contract, self.contract['checks'][0])
        self.assertEqual(receipt.read_bytes(), original)
        self.assertEqual(lock.read_text(), 'another runner owns this check')

    def test_reachable_state_without_resolution_is_rejected(self):
        flow = self.contract['workflows'][0]
        flow['states'].append('stuck')
        flow['transitions'].append({'from':'start','to':'stuck','guard':'lost response'})
        self.assert_gate('design', 'blocked')


if __name__ == "__main__":
    unittest.main()
