"""Run-local adapter for the pinned Qwen3.5 native tool template.

Only wire parsing changes. No entity/value repair, label access, or execution.
Like the existing native adapter, only the first call is proposed to AgentLoop.
"""
import copy
import json
import re

def parse_q35(raw, tools):
    text=raw.strip()
    text=re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()
    if '<think>' in text or '</think>' in text:
        raise ValueError('Incomplete thinking channel')
    blocks=list(re.finditer(r'<tool_call>(.*?)</tool_call>',text,re.S))
    meta={'blocks':len(blocks),'multi_block_turn':len(blocks)>1,'format_valid':True,'stop_kind':None}
    if not blocks:
        if any(t in text for t in ('<tool_call','</tool_call','<function=','<parameter=')):
            raise ValueError('Incomplete native XML call')
        if re.match(r'^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\s*(?:\(|\s+\w+=)',text):
            raise ValueError('Pseudo-call is not native XML')
        if text.startswith(('{','[')):
            obj=json.loads(text)
            if obj != {'stop':True}:
                raise ValueError('Bare JSON is not a native XML call')
        meta['stop_kind']='plain_text' if text else 'empty'
        return None,meta
    if text[blocks[-1].end():].strip():
        raise ValueError('Suffix after tool call is not permitted by template')
    match=re.fullmatch(r'\s*<function=([^<>\s]+)>(.*?)</function>\s*',blocks[0][1],re.S)
    if not match:
        raise ValueError('Missing native function wrapper')
    name,body=match.groups()
    if name not in tools:
        raise ValueError('Unknown function')
    properties=tools[name]['parameters'].get('properties',{})
    args={};cursor=0
    for param in re.finditer(r'<parameter=([^<>\s]+)>(.*?)</parameter>',body,re.S):
        if body[cursor:param.start()].strip():
            raise ValueError('Unexpected native parameter payload')
        key,value=param.groups();value=value.strip()
        if key in args or key not in properties:
            raise ValueError('Duplicate or unknown parameter')
        typ=properties[key].get('type','string')
        if typ!='string':
            value=json.loads(value)
            checks={'integer':lambda v:type(v) is int,
                    'number':lambda v:type(v) in (int,float),
                    'boolean':lambda v:type(v) is bool,
                    'array':lambda v:isinstance(v,list),
                    'object':lambda v:isinstance(v,dict)}
            if typ not in checks or not checks[typ](value):
                raise ValueError('Parameter has wrong JSON type')
        args[key]=value;cursor=param.end()
    if body[cursor:].strip():
        raise ValueError('Unparsed parameter payload')
    return {'name':name,'arguments':args},meta

def prepare_messages(messages):
    messages=copy.deepcopy(messages)
    messages[0]['content']=messages[0]['content'].replace(
        'Output one <tool_call> block containing name and arguments.',
        'Output one <tool_call> block using the function-call syntax specified above.')
    return messages
