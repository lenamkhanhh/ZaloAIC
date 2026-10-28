"""Read-only E5 audit. Run from repo after downloading v13 into result/."""
import copy,hashlib,json,re,sys,zipfile
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path.cwd()))
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root))
from e5_protocol import E5Protocol,ask_first
from lifemate.agent import AgentLoop
from lifemate.adapter import ZaicEnv
from lifemate.config import PipelineConfig
from lifemate.loader import load_split,load_catalog,catalog_tools_for_sample,fuzzy_params
from lifemate.scoring import score_sample
from lifemate.native_contract import parse_native,NativeFormatError
rule=(root/'rule.txt').read_text(encoding='utf8')
validated=json.loads((root/'cpu-result/e5_cpu/validated_inputs.json').read_text(encoding='utf8'))
plan=json.loads((root/'sample_plan.json').read_text());key=json.loads((root/'scoring_key_DIAGNOSTIC_ONLY.json').read_text())
data=Path('D:/Code/Code/AIO/Code/ZaloAIC/train+public_test/train+public_test')
samples={s.id:s for s in load_split(data,'train')};catalog=load_catalog(data,'train');fuzzy=fuzzy_params(catalog)
split=json.loads(Path('lifemate/splits/train_dev_heldout.json').read_text())
report={'scope':'E5_DIAGNOSTIC_ENGINEERING_PROXY_NOT_OFFICIAL','verified_trials':0,'generation_hashes_verified':0,'groups':{},'stats':{},'details':[]}
with zipfile.ZipFile(root/'result/lifemate_smoke/smoke_artifacts.zip') as z:
 assert z.testzip() is None
 summary=json.loads(z.read('summary.json'));assert summary['status']=='SMOKE_COMPLETED'
 assert summary['sample_plan']==plan and summary['source_commit']=='a472006441ec69aee1238153b0c7daf53ba41dee'
 with zipfile.ZipFile(root.parent/'lifemate-e6-c/v11-result/lifemate_smoke/smoke_artifacts.zip') as previous:
  prior=json.loads(previous.read('summary.json'))
  for field in ['models','dataset','seed','split_assignment_sha256','source_archive_sha256']:assert summary[field]==prior[field],field
  old_0116=json.loads(previous.read('pseudo_boundary_train_0116.json'))
  new_0116=json.loads(z.read('control_train_0116.json'))
  stable=lambda r:[{k:v for k,v in e.items() if k!='seconds'} for e in r['trace']]
  report['control_0116_v11_exact_match']=stable(old_0116)==stable(new_0116) and old_0116['submission']==new_0116['submission']
 for arm in ['control','rule']:
  stats=Counter();groups={g:{'correct':0,'total':0} for g in ['TARGET','CONTROL']}
  lines=[json.loads(x) for x in z.read('submission_'+arm+'.jsonl').decode().splitlines()]
  assert len(lines)==20 and [x['id'] for x in lines]==[x['id'] for x in plan]
  for line,item in zip(lines,plan):
   sid=line['id'];r=json.loads(z.read(arm+'_'+sid+'.json'));cached=validated['inputs'][sid]
   assert split[sid]=='dev' and r['status']=='INFERRED' and 'error' not in r
   assert r['model_current_transcript']==r['asr_transcript']==cached['current_asr'] and r['history_asr']==cached['history_asr']
   assert r['initial_prompt_sha256']==cached['prompt_sha256'][arm] and r['submission']==line
   expected=samples[sid].label['tool_calls'];assert expected==[{'name':'sys.ask_missing_info','arguments':key[sid]}]
   sample=copy.deepcopy(samples[sid])
   for t in sample.history:
    if t.role=='user' and t.audio:t.audio_text=cached['history_asr'][t.audio]
   gens=[e for e in r['trace'] if e['event']=='generation'];iterator=iter(gens);seen=[]
   def generator(messages,tools):
    event=next(iterator);seen.append(event)
    payload=json.dumps(messages,ensure_ascii=False,separators=(',',':'))
    assert hashlib.sha256(payload.encode()).hexdigest()==event['input_sha256']
    report['generation_hashes_verified']+=1
    try:call,diag=parse_native(event['raw_text'],reject_pseudo_calls=True)
    except NativeFormatError as exc:call={'name':'__invalid__','arguments':{'native_format_error':str(exc)}};diag=exc.diagnostics
    assert call==event['parsed'] and diag==event['native_diagnostics']
    return call
   actual=ZaicEnv(data,'train',sid)
   replay=AgentLoop(PipelineConfig(),catalog_tools_for_sample(catalog,sample)).run(sample,cached['current_asr'],actual,generator,protocol=E5Protocol(PipelineConfig(),rule if arm=='rule' else None))
   assert replay==line and len(seen)==len(gens)
   env,gold=ZaicEnv(data,'train',sid),ZaicEnv(data,'train',sid)
   for event in r['trace']:
    if event['event']=='tool':assert env.call(event['name'],event['arguments'])==event['result']
   assert env.submission_line()==line
   gold.call('sys.ask_missing_info',key[sid])
   assert score_sample(line,samples[sid],gold.state_hash(),fuzzy)==r['proxy']
   calls=line['tool_calls'];passed=ask_first(calls,key[sid])
   caught=sum(bool(e['native_diagnostics'].get('pseudo_call_caught')) for e in gens)
   silent=sum(e['parsed'] is None and bool(re.match(r'^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\s*\(',e['raw_text'].strip())) for e in gens)
   assert sum(e['event']=='validation_rejected' and e.get('stage')=='parser' for e in r['trace'])==caught
   first=calls[0] if calls else None
   first_kind=catalog_tools_for_sample(catalog,sample).get(first['name'],{}).get('kind') if first else None
   format_failure=bool(gens and not gens[-1]['native_diagnostics']['format_valid'])
   stats.update({'caught':caught,'silent':silent,'explicit_format_failure':format_failure,'premature_stop':not calls,'first_write':first_kind=='write','generations':len(gens),'submitted_calls':len(calls)})
   group=item['group'];groups[group]['correct']+=passed;groups[group]['total']+=1
   report['details'].append({'id':sid,'arm':arm,'group':group,'first_call':first,'ask_first':passed,'tool_name_only':bool(first and first['name']=='sys.ask_missing_info' and first['arguments'].get('tool_name')==key[sid]['tool_name']),'first_kind':first_kind,'caught':caught,'silent':silent,'explicit_format_failure':format_failure,'target_cue':validated['asr_cue'][sid],'proxy':r['proxy']})
   report['verified_trials']+=1
  report['groups'][arm]=groups;report['stats'][arm]=dict(stats)
 assert report['verified_trials']==40
 target_net=report['groups']['rule']['TARGET']['correct']-report['groups']['control']['TARGET']['correct']
 control_net=report['groups']['rule']['CONTROL']['correct']-report['groups']['control']['CONTROL']['correct']
 assert all(validated['asr_cue'][p['id']] for p in plan if p['group']=='TARGET'),'ASR-blocked target: report predeclared cue-present subset separately before verdict'
 if any(s['silent'] for s in report['stats'].values()):verdict='CONFOUNDED'
 elif target_net>=2 and control_net>=-1:verdict='CONFIRMED'
 elif target_net>=1 and control_net<=-2:verdict='PARTIAL'
 elif target_net==1 and control_net>=-1:verdict='INCONCLUSIVE'
 elif target_net<=0:verdict='REFUTED'
 else:raise AssertionError('Verdict not covered')
 report.update(target_net=target_net,control_net=control_net,verdict=verdict,elapsed_seconds=summary['elapsed_seconds'])
(root/'audited_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='details'},indent=2))
