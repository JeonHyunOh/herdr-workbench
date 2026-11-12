import importlib.util
from pathlib import Path
import unittest

class NativeEnvironmentContract(unittest.TestCase):
    def module(self):
        file = Path(__file__).resolve().parents[1] / 'native_exec.py'
        spec = importlib.util.spec_from_file_location('native_env_contract', file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_only_api_keys_are_removed_and_terminal_locale_identity_are_preserved(self):
        source = {'TERM':'screen-256color','COLORTERM':'24bit','LANG':'ko_KR.UTF-8',
                  'LC_CTYPE':'UTF-8','LC_MESSAGES':'C','HOME':'/home/example','PATH':'/bin:/example/bin',
                  'HC_TERMINAL_ID':'t-example','OTHER_SETTING':'keep',
                  'ANTHROPIC_API_KEY':'do-not-record-a','OPENAI_API_KEY':'do-not-record-b'}
        actual = self.module().native_environment(source)
        self.assertEqual(set(source) - set(actual), {'ANTHROPIC_API_KEY','OPENAI_API_KEY'})
        self.assertEqual(actual['COLORTERM'],'truecolor')
        for key in ['LANG','LC_CTYPE','LC_MESSAGES','HOME','PATH','HC_TERMINAL_ID','OTHER_SETTING']:
            self.assertEqual(actual[key],source[key])
        self.assertEqual(source['COLORTERM'],'24bit')

    def test_missing_or_empty_term_has_default_without_inventing_locale_or_home(self):
        for source in [{},{'TERM':''}]:
            actual = self.module().native_environment(source)
            self.assertEqual(actual['TERM'],'xterm-256color')
            self.assertEqual(actual['COLORTERM'],'truecolor')
            for absent in ['LANG','LC_ALL','HOME','PATH']:
                self.assertNotIn(absent,actual)

    def test_dumb_and_unknown_term_are_normalized_without_changing_real_terminals(self):
        module = self.module()
        for term in ['dumb', 'unknown']:
            with self.subTest(term=term):
                actual = module.native_environment({'TERM': term, 'COLORTERM': 'old'})
                self.assertEqual(actual['TERM'], 'xterm-256color')
                self.assertEqual(actual['COLORTERM'], 'truecolor')
        self.assertEqual(module.native_environment({'TERM': 'screen-256color'})['TERM'], 'xterm-256color')
