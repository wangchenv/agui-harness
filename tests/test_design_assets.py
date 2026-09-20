"""Schema examples and design checks are not browser/real-model acceptance."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import ui_audit
import harness


def load(relative):
    return json.loads((ROOT/relative).read_text())


class ApplicationSchemaTests(unittest.TestCase):
    def test_each_definition_accepts_valid_and_rejects_invalid_shape(self):
        schema=load('schemas/application.schema.json')
        Draft202012Validator.check_schema(schema)
        data=load('schemas/application-examples.json')
        self.assertEqual(set(data['definitions']),set(schema['$defs']))
        for name, values in data['definitions'].items():
            with self.subTest(definition=name):
                selected={'$schema':schema['$schema'],'$defs':schema['$defs'],'$ref':'#/$defs/'+name}
                validator=Draft202012Validator(selected)
                self.assertTrue(validator.is_valid(values['valid']))
                self.assertFalse(validator.is_valid(values['invalid']))

    def test_semantic_rejection_examples_remain_shape_valid_not_false_runtime_proof(self):
        schema=load('schemas/application.schema.json')
        for case in load('schemas/application-examples.json')['semantic_cases']:
            with self.subTest(case=case['name']):
                selected={'$defs':schema['$defs'],'$ref':'#/$defs/'+case['definition']}
                self.assertTrue(Draft202012Validator(selected).is_valid(case['instance']))
                self.assertTrue(case['expected_service_decision'])


class UIDesignTests(unittest.TestCase):
    def setUp(self):
        self.tokens=load('templates/tokens.json')
        self.inventory=load('templates/component-inventory.json')

    def test_default_declarations_pass(self):
        self.assertEqual(ui_audit.audit_tokens(self.tokens),[])
        self.assertEqual(ui_audit.audit_inventory(self.inventory),[])

    def test_known_contrast_endpoints(self):
        self.assertEqual(ui_audit.contrast('#000000','#ffffff'),21)
        self.assertEqual(ui_audit.contrast('#ffffff','#ffffff'),1)

    def test_low_contrast_rejected(self):
        self.tokens['color']['text_muted']='#cccccc'
        self.assertTrue(ui_audit.audit_tokens(self.tokens))

    def test_omitted_or_downgraded_text_pair_rejected(self):
        self.tokens['contrast_pairs'][0]['usage']='large_text'
        self.assertTrue(ui_audit.audit_tokens(self.tokens))
        self.tokens['contrast_pairs'].pop(0)
        self.assertTrue(ui_audit.audit_tokens(self.tokens))

    def test_unknown_colors_and_nonascending_breakpoints_rejected(self):
        self.tokens['contrast_pairs'][0]['foreground']='ghost'
        self.tokens['breakpoints_px']['mobile']=1000
        self.assertTrue(ui_audit.audit_tokens(self.tokens))

    def test_missing_component_rejected(self):
        self.inventory['screens'][0]['components']=['unknown-component']
        self.assertTrue(ui_audit.audit_inventory(self.inventory))

    def test_partial_unknown_and_unreceipted_writes_rejected(self):
        action=self.inventory['components'][0]['actions'][0]
        for state in ['partial','unknown','interrupted','submitting','committed']:
            with self.subTest(state=state):
                action['allowed_states']=[state]
                self.assertTrue(ui_audit.audit_inventory(self.inventory))
        action['allowed_states']=['validated'];action['result_source']='local'
        self.assertTrue(ui_audit.audit_inventory(self.inventory))

    def test_atomic_predicate_is_supported_and_requires_explanation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=(Path(tmp)/'component').resolve()
            shutil.copytree(ROOT/'examples/service-desk',project,ignore=shutil.ignore_patterns('__pycache__','evidence'))
            contract=harness.load_contract(project)
            tool=next(t for t in contract['tools'] if t['kind']=='write')
            tool['precondition']='atomic_predicate'
            self.assertTrue(any('precondition_detail' in x for x in harness.lint(project,contract)))
            tool['precondition_detail']='Backend exclusion constraint prevents overlapping reservations in one transaction; conflicts reject the original proposal.'
            self.assertEqual(harness.lint(project,contract),[])

    def test_ui_check_requires_browser_context(self):
        check={'kind':'ui','cases':['keyboard_navigation']}
        result={'schema_version':1,'cases':[{'id':'keyboard_navigation','status':'passed','detail':'fixture only'}]}
        self.assertTrue(harness.check_result(result,check))
        result['context']={'execution_mode':'browser'}
        self.assertTrue(harness.check_result(result,check))
        result['artifacts']=[{'path':'trace.zip','sha256':'a'*64}]
        self.assertEqual(harness.check_result(result,check),[])


if __name__=='__main__':unittest.main()
