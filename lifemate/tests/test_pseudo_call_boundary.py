"""E6-C synthetic parser boundary and retry regressions; no probe data."""
import unittest
from contextlib import nullcontext
from types import SimpleNamespace

from lifemate.agent import AgentLoop
from lifemate.config import PipelineConfig
from lifemate.loader import Sample
from lifemate.native_contract import NativeFormatError, NativeGenerator, NativeProtocol, parse_native
from lifemate.tests.test_native_contract import Tokenizer, Output, TOOLS


class PseudoCallBoundary(unittest.TestCase):
    def test_call_like_text_rejected_only_when_opted_in(self):
        for text in ('directory.search("tea")', '  phone.call ("person")',
                     'sys.ask_missing_info("directory.search", ["query"])',
                     'custom_2.action_3(unfinished'):
            with self.subTest(text=text):
                self.assertIsNone(parse_native(text)[0])
                with self.assertRaises(NativeFormatError) as caught:
                    parse_native(text, reject_pseudo_calls=True)
                self.assertTrue(caught.exception.diagnostics['pseudo_call_caught'])
                self.assertFalse(caught.exception.diagnostics['format_valid'])

    def test_real_prose_and_explicit_stops_preserved(self):
        for text in ('Done.', 'Tôi cần thêm thông tin.', 'The phone.call function needs a contact.',
                     '{"stop":true}', '', 'I will explain directory.search(query).'):
            with self.subTest(text=text):
                self.assertEqual(parse_native(text), parse_native(text, reject_pseudo_calls=True))

    def test_existing_tagged_calls_and_errors_preserved(self):
        tagged='<tool_call>{"name":"directory.search","arguments":{"query":"tea"}}</tool_call>'
        self.assertEqual(parse_native(tagged), parse_native(tagged, reject_pseudo_calls=True))
        for text in ('{"name":"directory.search","arguments":{}}', '<tool_call>unfinished'):
            with self.assertRaises(NativeFormatError): parse_native(text, reject_pseudo_calls=True)

    def run_loop(self, outputs):
        iterator=iter(outputs)
        tokenizer=Tokenizer()
        tokenizer.decode=lambda *a,**k: next(iterator)
        base=SimpleNamespace(tokenizer=tokenizer,model=SimpleNamespace(generate=lambda **k: Output()),
                             torch=SimpleNamespace(no_grad=nullcontext),device='cpu',
                             max_context_tokens=16384,max_tokens=512)
        generator=NativeGenerator(base,reject_pseudo_calls=True)
        attempts=[]
        def traced(messages,tools):
            result=generator(messages,tools)
            attempts.append(dict(generator.last_diagnostics))
            return result
        class Env:
            def __init__(self): self.calls=[]
            def validate(self,name,args): return {'ok':name in TOOLS,'error':'unknown function'}
            def call(self,name,args):
                self.calls.append({'name':name,'arguments':args})
                return {'ok':True}
            def submission_line(self): return {'tool_calls':self.calls}
        sample=Sample('synthetic','train','unused.wav',{'installed_apps':{}},[])
        result=AgentLoop(PipelineConfig(),TOOLS).run(sample,'Find tea',Env(),traced,
                                                    protocol=NativeProtocol(PipelineConfig()))
        return result,attempts

    def test_pseudo_call_retries_then_submits_tagged_ask(self):
        result,attempts=self.run_loop(['directory.search("tea")',
            '<tool_call>{"name":"sys.ask_missing_info","arguments":{"tool_name":"directory.search","params":["query"]}}</tool_call>'])
        self.assertEqual(len(attempts),2)
        self.assertTrue(attempts[0]['pseudo_call_caught'])
        self.assertEqual(result['tool_calls'],[{'name':'sys.ask_missing_info',
                         'arguments':{'tool_name':'directory.search','params':['query']}}])

    def test_retry_exhaustion_is_explicit_format_failure_without_execution(self):
        result,attempts=self.run_loop(['directory.search("tea")']*3)
        self.assertEqual(result['tool_calls'],[])
        self.assertEqual(len(attempts),3)
        self.assertTrue(all(a['pseudo_call_caught'] and not a['format_valid'] for a in attempts))

    def test_prose_and_stop_do_not_trigger_retry(self):
        for text in ('Đã xong.', '{"stop":true}'):
            result,attempts=self.run_loop([text])
            self.assertEqual(result['tool_calls'],[])
            self.assertEqual(len(attempts),1)
            self.assertTrue(attempts[0]['format_valid'])


if __name__=='__main__': unittest.main()
