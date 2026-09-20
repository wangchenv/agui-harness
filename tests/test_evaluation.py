"""All providers here are scripted fixtures, never actual model-quality evidence."""
import json
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from agui_eval.model import efficiency, evaluate


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.data = self.root / 'dataset.json'
        self.data.write_text(json.dumps({'dataset_id':'fixture-v1','scoring':'structured_exact_match','samples':[
            {'id':'a','input':{'x':1},'expected':{'value':1}},
            {'id':'b','input':{'x':2},'expected':{'value':2}}]}))
        self.prices = {'currency':'USD','model_version':'fixture-model-v1','input_per_million':1,'output_per_million':2}
        self.calls = 0
        def predict(value, **kwargs):
            self.calls += 1
            return {'output':{'value':value['x']},'model_version':'fixture-model-v1','request_id':str(self.calls),
                    'input_tokens':100,'output_tokens':50}
        self.provider = SimpleNamespace(EXECUTION_MODE='offline', predict=predict, __file__=__file__)

    def run_evaluation(self, **kwargs):
        return evaluate(self.provider,self.data,model='fixture-model-v1',prices=self.prices,
                        output_dir=self.root/'run',root=self.root,**kwargs)

    def test_offline_fixture_cannot_claim_live_quality(self):
        result = self.run_evaluation()
        self.assertEqual(result['context']['execution_mode'],'deterministic')
        self.assertEqual([c['status'] for c in result['cases']],['skipped','skipped'])
        self.assertEqual(result['metrics']['task_success_rate'],1)
        self.assertAlmostEqual(result['metrics']['cost_per_success'],.0002)
        self.assertEqual(len((self.root/'run/samples.jsonl').read_text().splitlines()),2)
        self.assertEqual(len(result['artifacts']),2)

    def test_live_flag_rejects_offline_provider_before_call(self):
        with self.assertRaises(ValueError): self.run_evaluation(live=True)
        self.assertEqual(self.calls,0)

    def test_sample_budget_enforced_before_call(self):
        with self.assertRaises(ValueError): self.run_evaluation(max_samples=1)
        self.assertEqual(self.calls,0)

    def test_failed_request_cannot_be_omitted_from_denominator(self):
        original = self.provider.predict
        def sometimes(value, **kwargs):
            if value['x']==2: raise TimeoutError('must not expose credential-bearing exception text')
            return original(value,**kwargs)
        self.provider.predict = sometimes
        self.provider.EXECUTION_MODE='live_model'  # Synthetic validator fixture only.
        result = self.run_evaluation(live=True)
        self.assertEqual(result['cases'][0]['status'],'failed')
        self.assertEqual(result['metrics']['sample_size'],2)
        self.assertEqual(result['metrics']['task_success_rate'],.5)
        raw=(self.root/'run/samples.jsonl').read_text()
        self.assertIn('TimeoutError',raw); self.assertNotIn('credential-bearing',raw)

    def test_missing_baseline_blocks_efficiency_despite_perfect_predictions(self):
        self.provider.EXECUTION_MODE='live_model'
        result = self.run_evaluation(live=True)
        self.assertEqual([c['status'] for c in result['cases']],['passed','skipped'])
        self.assertNotIn('human_time_reduction',result['metrics'])

    def test_paired_metrics_and_provenance_validation(self):
        baseline={'source_kind':'observed','study_id':'fixture-study','collected_at':'2026-09-20',
                  'population':'synthetic test fixture','baseline_version':'fixture-baseline','pairs':[
            {'sample_id':'a','baseline_seconds':100,'assisted_seconds':50,'baseline_rework':False,'assisted_rework':True},
            {'sample_id':'b','baseline_seconds':200,'assisted_seconds':100,'baseline_rework':True,'assisted_rework':False}]}
        self.assertEqual(efficiency(baseline,['a','b']),{'human_time_reduction':.5,'rework_delta':0})
        baseline['pairs'][1]['sample_id']='a'
        with self.assertRaises(ValueError): efficiency(baseline,['a','b'])

    def test_model_mismatch_fails_quality(self):
        original=self.provider.predict
        def wrong(*args,**kwargs):
            prediction=original(*args,**kwargs); prediction['model_version']='different'; return prediction
        self.provider.predict=wrong; self.provider.EXECUTION_MODE='live_model'
        result=self.run_evaluation(live=True)
        self.assertEqual(result['cases'][0]['status'],'failed')
        self.assertNotIn('cost_per_success',result['metrics'])

    def test_baseline_for_another_model_cannot_supply_efficiency(self):
        path=self.root/'baseline.json'
        path.write_text(json.dumps({'model_version':'wrong','dataset_id':'fixture-v1'}))
        self.provider.EXECUTION_MODE='live_model'
        result=self.run_evaluation(live=True,baseline_path=path)
        self.assertEqual(result['cases'][1]['status'],'skipped')

    def test_complete_paired_fixture_and_dataset_digest_binding(self):
        baseline={'source_kind':'observed','study_id':'fixture-study','collected_at':'2026-09-20',
                  'population':'synthetic unit fixture','baseline_version':'fixture-baseline',
                  'model_version':'fixture-model-v1','dataset_id':'fixture-v1',
                  'dataset_sha256':hashlib.sha256(self.data.read_bytes()).hexdigest(),
                  'pairs':[{'sample_id':sid,'baseline_seconds':100,'assisted_seconds':50,
                            'baseline_rework':False,'assisted_rework':False} for sid in ['a','b']]}
        path=self.root/'baseline.json'; path.write_text(json.dumps(baseline))
        self.provider.EXECUTION_MODE='live_model'  # Unit fixture, not a live experiment.
        result=self.run_evaluation(live=True,baseline_path=path)
        self.assertEqual([c['status'] for c in result['cases']],['passed','passed'])
        self.assertEqual(result['metrics']['human_time_reduction'],.5)
        self.data.write_text(self.data.read_text()+'\n')
        result=evaluate(self.provider,self.data,model='fixture-model-v1',prices=self.prices,
                        output_dir=self.root/'second',root=self.root,baseline_path=path,live=True)
        self.assertEqual(result['cases'][1]['status'],'skipped')


if __name__ == '__main__': unittest.main()
