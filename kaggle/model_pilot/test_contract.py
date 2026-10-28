"""Synthetic wire-format gates; no sample answers or model weights."""
import copy
import unittest

from contract import parse_q35, prepare_messages


TOOLS = {'demo.do': {'parameters': {'properties': {
    'text': {'type': 'string'}, 'amount': {'type': 'integer'},
    'ratio': {'type': 'number'}, 'enabled': {'type': 'boolean'},
    'items': {'type': 'array'}, 'meta': {'type': 'object'},
}}}}


def call(params, name='demo.do'):
    return '<tool_call>\n<function='+name+'>\n'+params+'\n</function>\n</tool_call>'


class ContractTests(unittest.TestCase):
    def test_scalar_and_structured_types(self):
        raw=call(''.join('<parameter='+k+'>\n'+v+'\n</parameter>\n' for k,v in
            [('text','00123'),('amount','1200'),('ratio','1.5'),('enabled','false'),
             ('items','["one", "two"]'),('meta','{"x": 1}')]))
        obj,meta=parse_q35(raw,TOOLS)
        self.assertEqual(obj['arguments'],dict(text='00123',amount=1200,ratio=1.5,
            enabled=False,items=['one','two'],meta={'x':1}))
        self.assertEqual(meta['blocks'],1)

    def test_free_text_is_preserved(self):
        obj,_=parse_q35(call('<parameter=text>\nhello\nworld & <tag>\n</parameter>'),TOOLS)
        self.assertEqual(obj['arguments']['text'],'hello\nworld & <tag>')

    def test_empty_arguments(self):
        obj,_=parse_q35(call(''),TOOLS)
        self.assertEqual(obj['arguments'],{})

    def test_prose_and_closed_thinking_before_call(self):
        obj,_=parse_q35('<think>ignore demo.fake()</think>\n'+call(''),TOOLS)
        self.assertEqual(obj['name'],'demo.do')

    def test_plain_stop(self):
        self.assertIsNone(parse_q35('All done.',TOOLS)[0])
        self.assertIsNone(parse_q35('{"stop":true}',TOOLS)[0])

    def test_invalid_never_becomes_clean_stop(self):
        cases=['demo.do(amount=2)','<tool_call>bad</tool_call>',
            '<tool_call><function=demo.do>', '<think>unfinished',
            call('<parameter=amount>invented</parameter>'),
            call('<parameter=missing>x</parameter>'),call('',name='demo.fake'),
            call('<parameter=text>x</parameter><parameter=text>y</parameter>'),
            call('<parameter=amount>true</parameter>'),
            call('<parameter=amount>1.5</parameter>'),
            call('<parameter=enabled>1</parameter>'),
            call('<parameter=items>{}</parameter>'),
            call('<parameter=meta>[]</parameter>'),
            call('unexpected payload'),call('')+' trailing text']
        for raw in cases:
            with self.subTest(raw=raw),self.assertRaises(ValueError):parse_q35(raw,TOOLS)

    def test_first_call_policy_matches_existing_agent(self):
        obj,meta=parse_q35(call('')+'\n'+call(''),TOOLS)
        self.assertEqual(obj['name'],'demo.do')
        self.assertTrue(meta['multi_block_turn'])

    def test_no_input_mutation(self):
        before=copy.deepcopy(TOOLS);parse_q35(call(''),TOOLS)
        self.assertEqual(TOOLS,before)

    def test_common_messages_only_remove_wire_specific_instruction(self):
        m=[{'role':'system','content':'Keep rules. Output one <tool_call> block containing name and arguments. When done, reply without a tool call.'},
           {'role':'user','content':'synthetic request'}]
        before=copy.deepcopy(m);p=prepare_messages(m)
        self.assertEqual(m,before);self.assertEqual(m[1:],p[1:])
        self.assertIn('Keep rules.',p[0]['content'])
        self.assertNotIn('containing name and arguments',p[0]['content'])


if __name__=='__main__':unittest.main(verbosity=2)
