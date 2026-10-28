import ast,copy,hashlib,json,re,sys,zipfile
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from lifemate.adapter import ZaicEnv
from lifemate.loader import load_catalog,load_split,fuzzy_params,catalog_tools_for_sample
from lifemate.scoring import score_sample
from lifemate.agent import AgentLoop
from lifemate.config import PipelineConfig
from lifemate.native_contract import NativeProtocol,NativeFormatError,parse_native
root=Path(__file__).resolve().parent
prior_audit=Path('../artifacts/lifemate-e1/v10-result/audit.py').read_text(encoding='utf-8-sig')
node=next(n for n in ast.parse(prior_audit).body if isinstance(n,ast.FunctionDef) and n.name=='prerequisites')
exec(compile(ast.Module(body=[node],type_ignores=[]),'frozen_prerequisites','exec'))
data=Path('D:/Code/Code/AIO/Code/ZaloAIC/train+public_test/train+public_test')
samples={s.id:s for s in load_split(data,'train')};catalog=load_catalog(data,'train');fuzzy=fuzzy_params(catalog)
inputs=json.loads((root.parent/'cached_inputs.json').read_text(encoding='utf8'))['inputs']
assignment=json.loads(Path('lifemate/splits/train_dev_heldout.json').read_text())
assert hashlib.sha256((root.parent/'E1_PREREQUISITE_CHECKLIST_FROZEN.md').read_bytes()).hexdigest()=='21b748c79ff3dff21f85805cffea8e3abe490ad902c5a0544aa260bb63ff60a1'
report={'scope':'E6_C_CHANNEL_DIAGNOSTIC_ENGINEERING_PROXY_NOT_OFFICIAL','verified_trials':0,'control_v10_matches':0,'all_generation_prompt_hash_matches':0,'stats':{},'details':[]}
with zipfile.ZipFile(root/'lifemate_smoke/smoke_artifacts.zip') as z,zipfile.ZipFile(root.parents[1]/'lifemate-e1/v10-result/lifemate_smoke/smoke_artifacts.zip') as old:
 assert z.testzip() is None
 summary=json.loads(z.read('summary.json'));prior=json.loads(old.read('summary.json'))
 assert summary['status']=='SMOKE_COMPLETED'
 assert summary['source_commit']=='a472006441ec69aee1238153b0c7daf53ba41dee'
 for k in ['models','dataset','sample_plan','seed','split_assignment_sha256']:assert summary[k]==prior[k],k
 for arm in ['native_control','pseudo_boundary']:
  stats=Counter();pass_count=0
  lines=[json.loads(l) for l in z.read(f'submission_{arm}.jsonl').decode().splitlines()]
  assert len(lines)==8 and [l['id'] for l in lines]==[x['id'] for x in summary['sample_plan']]
  for line in lines:
   sid=line['id'];record=json.loads(z.read(f'{arm}_{sid}.json'));previous=json.loads(old.read('native_'+sid+'.json'))
   assert record['status']=='INFERRED' and 'error' not in record and assignment[sid]=='dev'
   assert record['submission']==line
   assert record['asr_transcript']==record['model_current_transcript']==inputs[sid]['current_asr']
   assert record['history_asr']==inputs[sid]['history_asr']
   assert record['initial_prompt_sha256']==previous['initial_prompt_sha256']
   def stable_events(r):return [{k:v for k,v in e.items() if k!='seconds'} for e in r['trace']]
   if arm=='native_control':
    assert stable_events(record)==stable_events(previous) and line==previous['submission'];report['control_v10_matches']+=1
   elif sid!='train_0116':assert stable_events(record)==stable_events(previous) and line==previous['submission']
   sample=copy.deepcopy(samples[sid])
   for t in sample.history:
    if t.role=='user' and t.audio:t.audio_text=inputs[sid]['history_asr'][t.audio]
   generations=[e for e in record['trace'] if e['event']=='generation'];iterator=iter(generations);seen=[]
   def replay_generator(messages,tools):
    e=next(iterator);seen.append(e)
    payload=json.dumps(messages,ensure_ascii=False,separators=(',',':'))
    assert hashlib.sha256(payload.encode()).hexdigest()==e['input_sha256'],(arm,sid,len(seen))
    report['all_generation_prompt_hash_matches']+=1
    try:call,diag=parse_native(e['raw_text'],reject_pseudo_calls=(arm=='pseudo_boundary'))
    except NativeFormatError as exc:call={'name':'__invalid__','arguments':{'native_format_error':str(exc)}};diag=exc.diagnostics
    assert call==e['parsed'] and diag==e['native_diagnostics']
    return call
   replay=ZaicEnv(data,'train',sid)
   assert AgentLoop(PipelineConfig(),catalog_tools_for_sample(catalog,sample)).run(sample,inputs[sid]['current_asr'],replay,replay_generator,protocol=NativeProtocol(PipelineConfig()))==line
   assert len(seen)==len(generations)
   env,gold=ZaicEnv(data,'train',sid),ZaicEnv(data,'train',sid)
   for e in record['trace']:
    stats[e['event']]+=1
    if e['event']=='tool':assert env.call(e['name'],e['arguments'])==e['result']
   assert env.submission_line()==line
   for c in samples[sid].label['tool_calls']:gold.call(c['name'],c['arguments'])
   assert score_sample(line,samples[sid],gold.state_hash(),fuzzy)==record['proxy']
   caught=sum(bool(e['native_diagnostics'].get('pseudo_call_caught')) for e in generations)
   silent=sum(bool(re.match(r'^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\s*\(',e['raw_text'].strip())) and e['parsed'] is None for e in generations)
   parser_events=sum(e['event']=='validation_rejected' and e.get('stage')=='parser' for e in record['trace'])
   assert parser_events==caught
   format_failure=bool(generations and not generations[-1]['native_diagnostics']['format_valid'])
   stats['pseudo_caught']+=caught;stats['pseudo_silent']+=silent;stats['explicit_format_failure_samples']+=format_failure
   stats['correct_final_hash']+=record['proxy']['hash_correct']
   rel=prerequisites(sid,record['trace']);pass_count+=sum(v['pass'] for v in rel.values())
   report['details'].append({'id':sid,'arm':arm,'proxy':record['proxy'],'generations':len(generations),'pseudo_caught':caught,'pseudo_silent':silent,'explicit_format_failure':format_failure,'calls':line['tool_calls'],'relations':rel})
   report['verified_trials']+=1
  stats['prerequisite_pass']=pass_count;stats['prerequisite_total']=21;report['stats'][arm]=dict(stats)
 report['means']=summary['proxy_mean_by_arm'];report['elapsed_seconds']=summary['elapsed_seconds']
 assert report['control_v10_matches']==8 and report['verified_trials']==16
 boundary=next(d for d in report['details'] if d['arm']=='pseudo_boundary' and d['id']=='train_0116')
 assert boundary['pseudo_caught']==2 and boundary['pseudo_silent']==0 and boundary['explicit_format_failure'] and boundary['generations']==3 and not boundary['calls']
 report['verdict']='CONFIRMED_CHANNEL_ONLY_VIA_EXPLICIT_FAILURE_NOT_RECOVERED_ASK'
(root/'audited_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='details'},indent=2))
