"""Run-local E5 protocol; only the trial adds a frozen system rule."""
from lifemate.native_contract import NativeProtocol
from lifemate.agent import ACTION_POLICY

class E5Protocol(NativeProtocol):
    def __init__(self,config,rule=None):
        super().__init__(config)
        self.rule=rule
    def base(self,legacy,tools):
        messages=super().base(legacy,tools)
        if self.rule:
            rules=ACTION_POLICY.rsplit('\nOutput exactly',1)[0]
            assert messages[0]['content'].count(rules)==1
            messages[0]['content']=messages[0]['content'].replace(rules,rules+'\n'+self.rule,1)
        return messages

def ask_first(calls,expected):
    if not calls or calls[0]['name']!='sys.ask_missing_info': return False
    args=calls[0]['arguments']
    return args.get('tool_name')==expected['tool_name'] and set(args.get('params',[]))==set(expected['params'])
