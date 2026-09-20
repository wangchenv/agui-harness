import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('protection_audit',Path(__file__).resolve().parents[1]/'scripts/check_repository_protection.py')
audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class ProtectionTests(unittest.TestCase):
    def policy(self):
        return {'required_status_checks':{'strict':True,'checks':[{'context':'agui-required','app_id':15368}]},
                'enforce_admins':{'enabled':True},'allow_force_pushes':{'enabled':False},'allow_deletions':{'enabled':False}}

    def test_missing_controls_and_wrong_status_source_fail(self):
        self.assertEqual(audit.assess({},'agui-required')['status'],'blocked')
        policy=self.policy(); policy['required_status_checks']['checks'][0]['app_id']=None
        self.assertEqual(audit.assess(policy,'agui-required')['status'],'blocked')
        policy=self.policy(); policy['enforce_admins']['enabled']=False
        self.assertEqual(audit.assess(policy,'agui-required')['status'],'blocked')

    def test_explicit_complete_policy_passes_scoped_audit(self):
        self.assertEqual(audit.assess(self.policy(),'agui-required')['status'],'passed')


if __name__ == '__main__': unittest.main()
