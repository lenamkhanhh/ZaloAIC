"""E1 contract gates: synthetic only, no weights or probe answers."""
import copy
import json
from types import SimpleNamespace
import unittest

from lifemate.agent import AgentLoop, ACTION_POLICY, build_base_prompt
from lifemate.config import PipelineConfig
from lifemate.loader import Sample
from lifemate.llm import ContextBudgetExceeded

TOOLS = {
    'directory.search': {'name':'directory.search','kind':'read','description':'Find a person',
        'parameters':{'type':'object','properties':{'query':{'type':'string','x-match':'fuzzy'}},'required':['query']}},
    'phone.call': {'name':'phone.call','kind':'write','description':'Call a person',
        'parameters':{'type':'object','properties':{'contact_id':{'type':'string','x-ref':'directory.people'}},
                      'x-one-of':[['contact_id']]}},
    'sys.ask_missing_info': {'name':'sys.ask_missing_info','kind':'meta','description':'Ask',
        'parameters':{'type':'object','properties':{'tool_name':{'type':'string'},'params':{'type':'array','items':{'type':'string'}}},
                      'required':['tool_name','params']}},
}


class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        self.messages, self.kwargs = messages, kwargs
        return 'rendered'
    def encode(self, *args, **kwargs): return [1]*10
    def convert_tokens_to_ids(self, token): return 151645
    def __call__(self, *a, **k):
        return Encoded()
    def decode(self, *a, **k): return '<tool_call>{"name":"directory.search","arguments":{"query":"tea"}}</tool_call>'


class Encoded(dict):
    def __init__(self): super().__init__(input_ids=SimpleNamespace(shape=(1,3)))
    def to(self, device): return self


class Output:
    def __getitem__(self, key): return self


class NativeGates(unittest.TestCase):
    def sample(self): return Sample('synthetic','train','x.wav',{'installed_apps':{}},[])

    def test_conversion_recursive_metadata_strip_without_mutating_catalog(self):
        from lifemate.native_contract import function_definitions
        before = copy.deepcopy(TOOLS)
        defs = function_definitions(TOOLS)
        self.assertEqual(TOOLS,before)
        self.assertTrue(all(set(d)=={'type','function'} for d in defs))
        self.assertNotIn('x-ref',json.dumps(defs))
        self.assertNotIn('x-match',json.dumps(defs))
        self.assertNotIn('x-one-of',json.dumps(defs))
        self.assertEqual(defs[-1]['function']['parameters']['required'],['tool_name','params'])

    def test_messages_preserve_user_content_and_policy_rules(self):
        from lifemate.native_contract import NativeProtocol
        raw = build_base_prompt(self.sample(),'Find tea',TOOLS)
        suffix = '\nRead only to resolve a missing entity or precondition; reuse still-valid observations.'
        protocol = NativeProtocol(PipelineConfig())
        messages = protocol.base(raw+suffix+'\nDo not add a verification read after a write unless the next action needs its result.',TOOLS)
        self.assertEqual([m['role'] for m in messages],['system','user'])
        self.assertIn(ACTION_POLICY.rsplit('\nOutput exactly',1)[0],messages[0]['content'])
        self.assertIn('Current user request (transcript): Find tea',messages[1]['content'])
        self.assertNotIn('Tools you may call',messages[1]['content'])
        self.assertNotIn('Find a person',messages[1]['content'])
        result = {'ok':True,'people':[{'id':'p7','name':'Tea'}]}
        expanded = protocol.render(messages,[{'name':'directory.search','arguments':{'query':'Tea'}}],[result])
        self.assertEqual([m['role'] for m in expanded],['system','user','assistant','tool'])
        self.assertEqual(json.loads(expanded[-1]['content']),result)
        self.assertEqual(messages[1]['content'],expanded[1]['content'])

    def test_render_passes_native_tools_and_checks_reserved_budget(self):
        from lifemate.native_contract import render_native
        tokenizer = Tokenizer()
        self.assertEqual(render_native(tokenizer,[{'role':'user','content':'hi'}],TOOLS,32,16),'rendered')
        self.assertIn('tools',tokenizer.kwargs)
        self.assertIs(tokenizer.kwargs['add_generation_prompt'],True)
        with self.assertRaises(ContextBudgetExceeded): render_native(tokenizer,[],TOOLS,20,16)

    def test_parser_stops_bare_call_rejects_and_first_block_only(self):
        from lifemate.native_contract import parse_native, NativeFormatError
        for text in ('Done.', '', '{"stop":true}', '{"name":"stop"}'):
            self.assertIsNone(parse_native(text)[0])
        for text in ('{"name":"phone.call","arguments":{}}', '<tool_call>{bad}</tool_call>',
                     '<tool_call>{"name":"x","arguments":[]}</tool_call>', '<tool_call>unfinished',
                     '```json\n{"name":"phone.call","arguments":{}}\n```'):
            with self.assertRaises(NativeFormatError): parse_native(text)
        call, diagnostics = parse_native('<tool_call>{"name":"x","arguments":"{\\"a\\":1}"}</tool_call>'
                                         '<tool_call>{"name":"y","arguments":{}}</tool_call>')
        self.assertEqual(call,{'name':'x','arguments':{'a':1}})
        self.assertEqual(diagnostics['blocks'],2)
        self.assertTrue(diagnostics['arguments_string_decoded'])

    def test_transformers_native_stop_is_explicit_and_single_call(self):
        from contextlib import nullcontext
        from lifemate.native_contract import NativeGenerator
        captured={}
        def generate(**kwargs): captured.update(kwargs); return Output()
        base=SimpleNamespace(tokenizer=Tokenizer(),model=SimpleNamespace(generate=generate),
            torch=SimpleNamespace(no_grad=nullcontext),device='cpu',max_context_tokens=32,max_tokens=16)
        native=NativeGenerator(base)
        self.assertEqual(native([{'role':'user','content':'hi'}],TOOLS)['name'],'directory.search')
        self.assertEqual(captured['eos_token_id'],151645)
        self.assertIs(captured['do_sample'],False)
        self.assertTrue(native.last_diagnostics['format_valid'])

    def test_vllm_stop_is_explicit(self):
        from unittest.mock import patch
        from lifemate.native_contract import NativeGenerator
        import types
        params={}
        def sample(**kwargs): params.update(kwargs); return kwargs
        engine=SimpleNamespace(generate=lambda text,p:[SimpleNamespace(outputs=[SimpleNamespace(text='Done.')])])
        base=SimpleNamespace(tokenizer=Tokenizer(),llm=engine,max_context_tokens=32,max_tokens=16)
        with patch.dict('sys.modules',{'vllm':types.SimpleNamespace(SamplingParams=sample)}):
            native=NativeGenerator(base)
            self.assertIsNone(native([{'role':'user','content':'hi'}],TOOLS))
        self.assertEqual(params['stop_token_ids'],[151645])

    def test_loop_native_and_legacy_execute_equivalent_synthetic_trace(self):
        from lifemate.native_contract import NativeProtocol
        class Env:
            def __init__(self): self.calls=[]
            def validate(self,n,a): return {'ok':True}
            def call(self,n,a):
                self.calls.append({'name':n,'arguments':a})
                return {'ok':True,'people':[{'id':'p7','name':'Tea'}]}
            def submission_line(self): return {'tool_calls':self.calls}
        outputs=[]
        for native in (False,True):
            env=Env()
            def gen(prompt,tools):
                if not env.calls: return {'name':'directory.search','arguments':{'query':'Tea'}}
                if len(env.calls)==1:
                    self.assertIn('p7',json.dumps(prompt))
                    return {'name':'phone.call','arguments':{'contact_id':'p7'}}
                return None
            kwargs={'protocol':NativeProtocol(PipelineConfig())} if native else {}
            outputs.append(AgentLoop(PipelineConfig(),TOOLS).run(self.sample(),'Call Tea',env,gen,**kwargs))
        self.assertEqual(outputs[0],outputs[1])


if __name__=='__main__': unittest.main()
