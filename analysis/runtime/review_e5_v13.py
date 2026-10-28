"""Manual raw-stop review and predeclared diagnosis, without changing verdict."""
import json,zipfile
from collections import Counter
from pathlib import Path
root=Path(__file__).resolve().parent
r=json.loads((root/'audited_results.json').read_text(encoding='utf8'))
key=json.loads((root/'scoring_key_DIAGNOSTIC_ONLY.json').read_text())
review=[];counts={};diagnoses={};trace_outcomes={}
with zipfile.ZipFile(root/'result/lifemate_smoke/smoke_artifacts.zip') as z:
 for arm in ['control','rule']:
  buckets=Counter();primary=Counter();outcomes=Counter();gap_count=0;true_clean=0
  for d in [x for x in r['details'] if x['arm']==arm]:
   rec=json.loads(z.read(arm+'_'+d['id']+'.json'));gens=[e for e in rec['trace'] if e['event']=='generation']
   for i,g in enumerate(gens):
    diag=g['native_diagnostics']
    if diag.get('blocks',0)>=1 and diag['format_valid']:bucket='tagged'
    elif diag.get('pseudo_call_caught'):bucket='caught'
    elif diag.get('stop_kind')=='plain_text':bucket='plain_text'
    elif diag.get('stop_kind')=='legacy_stop':bucket='legacy_stop'
    elif diag.get('stop_kind')=='empty':bucket='empty_stop'
    else:bucket='other_format_error'
    buckets[bucket]+=1
    if bucket=='plain_text':
     gap=g['raw_text'].startswith('sys.ask_missing_info tool_name=')
     # Every plain-text output was read in full before recording these annotations.
     if gap:
      assert d['id']=='train_0653' and len(rec['submission']['tool_calls'])==1
      gap_count+=1
     review.append({'id':d['id'],'arm':arm,'generation_index':i+1,'raw_text':g['raw_text'],'manual_review':'UNSUBMITTED_PSEUDO_AFTER_READ' if gap else 'ordinary_prose','zero_submitted_trace':not rec['submission']['tool_calls']})
   if not d['first_call'] and d['explicit_format_failure']:diagnosis='CHANNEL_CAUGHT_FAILED'
   elif not d['first_call'] and d['silent']:diagnosis='CHANNEL_SILENT'
   elif not d['first_call']:diagnosis='PREMATURE_STOP'
   elif d['group']=='TARGET' and not d['target_cue']:diagnosis='ASR_CUE_LOSS'
   elif d['first_call']['name']!='sys.ask_missing_info' or d['first_call']['arguments'].get('tool_name')!=key[d['id']]['tool_name']:diagnosis='WRONG_INTENT_OR_ASK_VS_ACT'
   elif set(d['first_call']['arguments'].get('params',[]))!=set(key[d['id']]['params']):diagnosis='WRONG_ASK_PARAMS'
   else:diagnosis='PASS'
   d['primary_diagnosis']=diagnosis;primary[diagnosis]+=1
   if d['first_call']:outcome='RETURNED_WITH_CALLS'
   elif d['explicit_format_failure']:outcome='FORMAT_FAILURE_RETRY_EXHAUSTED'
   elif d['silent']:outcome='SILENT_PSEUDO'
   else:outcome='CLEAN_ZERO_CALL_STOP';true_clean+=1
   d['trace_outcome']=outcome;outcomes[outcome]+=1
   d['parser_scope_gap_after_submitted_call']=(d['id']=='train_0653')
  assert sum(buckets.values())==r['stats'][arm]['generations']
  r['stats'][arm]['manual_scope_gap_after_calls']=gap_count
  r['stats'][arm]['clean_zero_call_stops']=true_clean
  counts[arm]=dict(buckets);diagnoses[arm]=dict(primary);trace_outcomes[arm]=dict(outcomes)
r['generation_partition']=counts;r['primary_diagnosis_counts']=diagnoses;r['trace_outcomes']=trace_outcomes
r['manual_plain_text_review_count']=len(review)
r['verdict_scope']='INCONCLUSIVE under preregistered zero-submission silent definition; one unsubmitted key=value pseudo-stop after an already submitted read in each arm remains a channel limitation. Broader all-output silent interpretation would be CONFOUNDED; not substituted for the primary verdict after observing results.'
(root/'audited_results.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
(root/'plain_text_stop_review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'generation_partition':counts,'primary_diagnosis_counts':diagnoses,'trace_outcomes':trace_outcomes,'manual_review_count':len(review),'registered_verdict':r['verdict']},indent=2))
