"""Opt-in E1 protocol, not the default or a promoted model configuration.

Wire source: Qwen/Qwen3-4B-Instruct-2507 tokenizer_config.json at
cdbee75f17c01a7cc42f958dc650907174af0554. One tool call per turn is retained.
History stays prose; only this turn's observed calls become native messages.
"""
from __future__ import annotations

import copy
import json
import re

from .agent import ACTION_POLICY
from .llm import ContextBudgetExceeded, is_stop_signal

EOS_ID = 151645


def function_definitions(tools):
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(child) for key, child in value.items() if not key.startswith('x-')}
        if isinstance(value, list):
            return [clean(child) for child in value]
        return value
    return [{'type':'function','function':{'name':name,'description':spec.get('description',''),
            'parameters':clean(spec['parameters'])}} for name,spec in sorted(tools.items())]


class NativeProtocol:
    def __init__(self, config):
        self.config = config

    def base(self, legacy, tools):
        suffix = []
        if self.config.selective_reads:
            suffix.append('Read only to resolve a missing entity or precondition; reuse still-valid observations.')
        if not self.config.verification_read_after_write:
            suffix.append('Do not add a verification read after a write unless the next action needs its result.')
        for line in reversed(suffix):
            if not legacy.endswith('\n'+line):
                raise ValueError('Unexpected config suffix in native contract input')
            legacy = legacy[:-len(line)-1]
        before_tools, sep, _ = legacy.partition('\nTools you may call (this sample only):\n')
        if not sep:
            raise ValueError('Missing legacy tool-list boundary')
        instruction, user_context = before_tools.split('\n'+ACTION_POLICY+'\n',1)
        instruction = re.sub(r'Output exactly one JSON object per turn: .*? when done\.',
            'Output one <tool_call> block per turn; when done, reply with plain text and no tool call.', instruction)
        # Keep all decision rules verbatim. Their legacy stop JSON is accepted
        # as an unambiguous stop by the native parser, not as a function call.
        rules = ACTION_POLICY.rsplit('\nOutput exactly',1)[0]
        system = '\n'.join([instruction,rules,*suffix,
            'Output one <tool_call> block containing name and arguments. When done, reply without a tool call.'])
        _, sep, history = legacy.partition('\nConversation history:\n')
        if not sep:
            raise ValueError('Missing history boundary')
        return [{'role':'system','content':system},
                {'role':'user','content':user_context+'\nConversation history:\n'+history}]

    def render(self, base, executed, results, replan=False):
        messages = copy.deepcopy(base)
        for call,result in zip(executed,results):
            messages.append({'role':'assistant','content':'','tool_calls':[
                {'type':'function','function':copy.deepcopy(call)}]})
            messages.append({'role':'tool','name':call['name'],
                             'content':json.dumps(result,ensure_ascii=False,separators=(',',':'))})
        if replan:
            messages.append({'role':'user','content':'Choose a different, evidence-backed action or finish without a tool call.'})
        return messages

    def feedback(self, messages, text):
        return messages + [{'role':'user','content':
            'Your last output was not a valid <tool_call> block. Output one <tool_call> block, or plain text with no tool call when done.'}]


def render_native(tokenizer, messages, tools, context_cap, output_tokens):
    text = tokenizer.apply_chat_template(messages,tools=function_definitions(tools),
                                        tokenize=False,add_generation_prompt=True)
    size = len(tokenizer.encode(text,add_special_tokens=False))
    if size + output_tokens > context_cap:
        raise ContextBudgetExceeded(f'native prompt={size} + reserved_output={output_tokens} exceeds context={context_cap}')
    return text


class NativeFormatError(ValueError):
    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = {**diagnostics,'format_valid':False,'format_error':message}


def parse_native(text):
    text = text.strip()
    blocks = re.findall(r'<tool_call>\s*(.*?)\s*</tool_call>',text,re.DOTALL)
    meta = {'blocks':len(blocks),'multi_block_turn':len(blocks)>1,
            'arguments_string_decoded':False,'format_valid':True,'stop_kind':None}
    def fail(message): raise NativeFormatError(message,meta)
    if blocks:
        try:
            obj = json.loads(blocks[0])
        except (ValueError,TypeError):
            fail('Malformed first tool_call JSON')
        if not isinstance(obj,dict) or not isinstance(obj.get('name'),str) or not obj['name']:
            fail('Native call requires a nonempty string name')
        arguments = obj.get('arguments')
        if isinstance(arguments,str):
            try:
                arguments = json.loads(arguments)
            except (ValueError,TypeError):
                fail('Native arguments string is not JSON')
            meta['arguments_string_decoded'] = True
        if not isinstance(arguments,dict):
            fail('Native call arguments must be an object')
        return {'name':obj['name'],'arguments':arguments},meta
    if '<tool_call' in text or '</tool_call' in text:
        fail('Incomplete tool_call tags')
    candidate = text
    fence = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```',text,re.DOTALL)
    if fence:
        candidate = fence[1]
    try:
        obj = json.loads(candidate)
    except ValueError:
        if candidate.startswith(('{','[')):
            fail('Malformed bare JSON without native tags')
        meta['stop_kind'] = 'plain_text' if text else 'empty'
        return None,meta
    if is_stop_signal(obj):
        meta['stop_kind'] = 'legacy_stop'
        return None,meta
    fail('Bare JSON call is not native tool_call format')


class NativeGenerator:
    """Share an already loaded legacy generator's weights; no second model."""
    def __init__(self, base, seed=42):
        self.base, self.seed = base, seed
        self.last_diagnostics = {}
        if base.tokenizer.convert_tokens_to_ids('<|im_end|>') != EOS_ID:
            raise ValueError('Unexpected Qwen EOS: E1 requires the pinned tokenizer')

    def __call__(self, messages, tools):
        base = self.base
        text = render_native(base.tokenizer,messages,tools,base.max_context_tokens,base.max_tokens)
        if hasattr(base,'model'):
            ids = base.tokenizer(text,return_tensors='pt',add_special_tokens=False).to(base.device)
            with base.torch.no_grad():
                output = base.model.generate(**ids,max_new_tokens=base.max_tokens,do_sample=False,eos_token_id=EOS_ID)
            decoded = base.tokenizer.decode(output[0][ids['input_ids'].shape[1]:],skip_special_tokens=True)
        else:
            from vllm import SamplingParams
            params = SamplingParams(temperature=0.0,seed=self.seed,max_tokens=base.max_tokens,stop_token_ids=[EOS_ID])
            decoded = base.llm.generate([text],params)[0].outputs[0].text
        try:
            call,self.last_diagnostics = parse_native(decoded)
            return call
        except NativeFormatError as exc:
            self.last_diagnostics = exc.diagnostics
            return {'name':'__invalid__','arguments':{'native_format_error':str(exc)}}
