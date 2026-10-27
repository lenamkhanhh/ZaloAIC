import copy,hashlib,json,sys,zipfile
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path.cwd()))
from lifemate.adapter import ZaicEnv
from lifemate.loader import load_catalog,load_split,fuzzy_params,catalog_tools_for_sample
from lifemate.scoring import score_sample
from lifemate.agent import AgentLoop
from lifemate.config import PipelineConfig
from lifemate.native_contract import NativeProtocol,parse_native
root=Path(__file__).resolve().parent
data=Path('D:/Code/Code/AIO/Code/ZaloAIC/train+public_test/train+public_test')
samples={s.id:s for s in load_split(data,'train')};catalog=load_catalog(data,'train');fuzzy=fuzzy_params(catalog)
cached=json.loads((root.parent/'cached_inputs.json').read_text(encoding='utf8'))['inputs']
assignment=json.loads(Path('lifemate/splits/train_dev_heldout.json').read_text())
relations={};details=[];stats={arm:Counter() for arm in ['text','native']}
def prerequisites(sid,events):
 calls=[e for e in events if e['event']=='tool']; names=[c['name'] for c in calls]
 def has(n):return n in names
 def before(a,b):return has(a) and has(b) and names.index(a)<names.index(b)
 def contains(value,obj):return value in json.dumps(obj,ensure_ascii=False)
 def observed_before(value,dependent):
  return has(dependent) and any(c['name']=='contacts.search' and contains(value,c['result']) for c in calls[:names.index(dependent)])
 def pair(key,passed,dependent=None):
  return key,{'pass':bool(passed),'secondary':('NOT_EXECUTED' if dependent and not has(dependent) else 'PASS' if passed else 'EXECUTED_WITHOUT_PREREQUISITE' if dependent else 'FAIL')}
 if sid.endswith('0019'):return dict([pair('R19.1',not calls)])
 if sid.endswith('0116'):return dict([pair('R116.1',len(calls)==1 and calls[0]['name']=='sys.ask_missing_info' and calls[0]['arguments']=={'tool_name':'reminders.create','params':['time']})])
 if sid.endswith('0025'):return dict([pair('R25.1',before('weather.get_forecast','calendar.cancel_event'),'calendar.cancel_event'),pair('R25.2',before('calendar.list_events','calendar.cancel_event'),'calendar.cancel_event'),pair('R25.3',before('contacts.search','sys.ask_missing_info'),'sys.ask_missing_info'),pair('R25.4',not has('phone.call'))])
 if sid.endswith('0003'):return dict([pair('R03.1',observed_before('09919377320','ewallet.topup_mobile'),'ewallet.topup_mobile'),pair('R03.2',before('bill_payment.list_bills','ewallet.transfer'),'ewallet.transfer'),pair('R03.3',observed_before('c_06','ewallet.transfer'),'ewallet.transfer')])
 if sid.endswith('0008'):return dict([pair('R08.1',bool(calls) and names[0]=='weather.get_forecast' and calls[0]['arguments'].get('date')=='2026-11-14'),pair('R08.2',not has('alarm.update')),pair('R08.3',not has('weather.get_current'))])
 if sid.endswith('0016'):return dict([pair('R16.1',before('weather.get_forecast','calendar.update_event'),'calendar.update_event'),pair('R16.2',before('calendar.list_events','calendar.update_event'),'calendar.update_event'),pair('R16.3',observed_before('c_01','sms.send'),'sms.send'),pair('R16.4',not has('reminders.create') and not has('reminders.complete'))])
 if sid.endswith('0049'):return dict([pair('R49.1',before('bill_payment.list_bills','banking.transfer'),'banking.transfer'),pair('R49.2',before('banking.get_balance','banking.transfer'),'banking.transfer'),pair('R49.3',before('banking.list_beneficiaries','banking.transfer'),'banking.transfer'),pair('R49.4',not has('banking.open_savings'))])
 if sid.endswith('0004'):return dict([pair('R04.1',before('smart_home.get_status','smart_home.light_set'),'smart_home.light_set')])
 raise ValueError(sid)
with zipfile.ZipFile(root/'lifemate_smoke/smoke_artifacts.zip') as z,zipfile.ZipFile(root.parents[1]/'lifemate-agent-v7/result/lifemate_smoke/smoke_artifacts.zip') as old:
 assert z.testzip() is None
 summary=json.loads(z.read('summary.json')); prior=json.loads(old.read('summary.json'))
 assert summary['status']=='SMOKE_COMPLETED'
 for k in ['models','dataset','sample_plan','seed','split_assignment_sha256']:assert summary[k]==prior[k],k
 for arm in ['text','native']:
  relations[arm]={}
  lines=[json.loads(l) for l in z.read(f'submission_{arm}.jsonl').decode().splitlines()]
  assert len(lines)==8 and [l['id'] for l in lines]==[x['id'] for x in summary['sample_plan']]
  for line in lines:
   sid=line['id'];r=json.loads(z.read(f'{arm}_{sid}.json')); v7=json.loads(old.read(sid+'.json'))
   assert assignment[sid]=='dev' and r['status']=='INFERRED' and 'error' not in r
   assert r['submission']==line and r['history_asr']==cached[sid]['history_asr'] and r['model_current_transcript']==cached[sid]['current_asr']
   sample=copy.deepcopy(samples[sid])
   for t in sample.history:
    if t.role=='user' and t.audio:t.audio_text=cached[sid]['history_asr'][t.audio]
   first=[]
   class EmptyEnv:
    def submission_line(self):return {'tool_calls':[]}
   def capture(prompt,tools):first.append(prompt);return None
   AgentLoop(PipelineConfig(),catalog_tools_for_sample(catalog,sample)).run(sample,cached[sid]['current_asr'],EmptyEnv(),capture,protocol=NativeProtocol(PipelineConfig()) if arm=='native' else None)
   payload=first[0] if arm=='text' else json.dumps(first[0],ensure_ascii=False,separators=(',',':'))
   assert hashlib.sha256(payload.encode()).hexdigest()==r['initial_prompt_sha256']
   if arm=='text':
    assert r['initial_prompt_sha256']==v7['initial_prompt_sha256']
    assert line==v7['submission']
    assert [e.get('raw_text') for e in r['trace'] if e['event']=='generation']==[e.get('raw_text') for e in v7['trace'] if e['event']=='generation']
   env,gold=ZaicEnv(data,'train',sid),ZaicEnv(data,'train',sid)
   for event in r['trace']:
    stats[arm][event['event']]+=1
    if event['event']=='tool':assert env.call(event['name'],event['arguments'])==event['result']
    if event['event']=='generation' and arm=='native':
     call,diag=parse_native(event['raw_text']);assert call==event['parsed'] and diag==event['native_diagnostics']
     stats[arm]['native_'+str(diag['stop_kind'] or 'tool_call')]+=1
     if diag['stop_kind']=='plain_text' and 'sys.ask_missing_info(' in event['raw_text']:stats[arm]['pseudo_call_plain_text']+=1
   assert env.submission_line()==line
   for c in samples[sid].label['tool_calls']:gold.call(c['name'],c['arguments'])
   assert score_sample(line,samples[sid],gold.state_hash(),fuzzy)==r['proxy']
   rel=prerequisites(sid,r['trace']);relations[arm][sid]=rel
   details.append({'id':sid,'arm':arm,'proxy':r['proxy'],'calls':line['tool_calls'],'relations':rel})
 assert all(sum(len(x) for x in relations[a].values())==21 for a in relations)
report={'scope':'ENGINEERING_PROXY_NOT_OFFICIAL','verified_trials':16,'replay_and_proxy_matches':16,'text_v7_exact_trace_matches':8,'input_hash_matches':16,'elapsed_seconds':summary['elapsed_seconds'],'means':summary['proxy_mean_by_arm'],'stats':{a:dict(c) for a,c in stats.items()},'prerequisite_pass':{a:sum(v['pass'] for rel in ss.values() for v in rel.values()) for a,ss in relations.items()},'prerequisite_denominator':21,'details':details}
(root/'audited_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='details'},indent=2))
