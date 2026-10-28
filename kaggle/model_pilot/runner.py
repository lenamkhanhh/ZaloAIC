"""Eight paired dev diagnostics, gold current AND history, no ASR/training.

Executed in a bounded subprocess by the notebook. Uses immutable mounted
data/source, an embedded contract adapter, and model-native chat templates.
Not an A30 latency or representative quality benchmark.
"""
import copy
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import zipfile
from contextlib import contextmanager

BASE_COMMIT='a472006441ec69aee1238153b0c7daf53ba41dee'
DATA_SHA='57d371518996ec70d3af86402b7eba61208093c82955b9807a7ab39604b47320'
SOURCE_SHA='9a61bda65ff00253a906804f6e0aa81cf0feda4af2300e0e58ae775f60c0b5dc'
IDS=['train_0019','train_0116','train_0025','train_0003','train_0008','train_0016','train_0049','train_0004']
MODELS=[{'arm':'qwen3','checkpoint':'Qwen/Qwen3-4B-Instruct-2507',
         'revision':'cdbee75f17c01a7cc42f958dc650907174af0554','params':4022468096},
        {'arm':'qwen35','checkpoint':'Qwen/Qwen3.5-4B',
         'revision':'851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a','params':4659865088}]
OUT=Path('/kaggle/working/model_pilot')
WORK=Path('/kaggle/temp/model_pilot')


def write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def extract(path,dest):
    dest=dest.resolve()
    with zipfile.ZipFile(path) as z:
        for item in z.infolist():
            if not (dest/item.filename).resolve().is_relative_to(dest):raise ValueError('Unsafe ZIP path')
        z.extractall(dest)


@contextmanager
def heartbeat(label):
    done=threading.Event();started=time.monotonic()
    def pulse():
        while not done.wait(15):print('ALIVE',label,round(time.monotonic()-started,1),flush=True)
    worker=threading.Thread(target=pulse,daemon=True);worker.start()
    print('START',label,flush=True)
    try:yield
    finally:done.set();worker.join(timeout=1);print('END',label,round(time.monotonic()-started,1),flush=True)


def main():
    OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
    summary={'status':'RUNNING','scope':'DEV8_FULL_GOLD_DIAGNOSTIC_NOT_BENCHMARK',
             'base_source_commit':BASE_COMMIT,'data_sha256':DATA_SHA,'ids':IDS,
             'models':MODELS,'seed':42,'max_steps':12,'max_new_tokens':512,
             'max_context_tokens':16384,'thinking':False,'sample_soft_limit_s':240,
             'generation_soft_limit_s':90,'attention':'HF repeat_kv + efficient SDPA on T4',
             'protocol_change':'Same wire-neutral final sentence for BOTH arms; NOT a V11 reproduction',
             'quantization':None,'dtype':'float16','asr':'NONE; gold current + every history user',
             'privacy':'private notebook; no friend private source or weights', 'arms':{}}
    write(OUT/'summary.json',summary)
    try:
        from contract import parse_q35,prepare_messages
        with heartbeat('mounted_input_verification'):
            data=list(Path('/kaggle/input').rglob('lifemate-v3.2.0.zip.bin'))
            source=list(Path('/kaggle/input').rglob('source-e6.zip.bin'))
            assert len(data)==len(source)==1
            assert digest(data[0])==DATA_SHA and digest(source[0])==SOURCE_SHA
            extract(source[0],WORK/'source');extract(data[0],WORK/'data')
        repo=WORK/'source'/('ZaloAIC-'+BASE_COMMIT)
        sys.path.insert(0,str(repo));root=WORK/'data'/'train+public_test'
        from lifemate.agent import AgentLoop,build_base_prompt
        from lifemate.config import PipelineConfig
        from lifemate.loader import load_split,load_catalog,catalog_tools_for_sample,fuzzy_params
        from lifemate.adapter import ZaicEnv
        from lifemate.native_contract import NativeProtocol,function_definitions,parse_native
        from lifemate.scoring import score_sample,summarise
        samples={s.id:s for s in load_split(root,'train')};catalog=load_catalog(root,'train')
        split=json.loads((repo/'lifemate/splits/train_dev_heldout.json').read_text())
        assert all(split[sid]=='dev' for sid in IDS)
        cfg=PipelineConfig.from_json(repo/'lifemate/configs/recommended.json')
        class Protocol(NativeProtocol):
            def base(self,legacy,tools):return prepare_messages(super().base(legacy,tools))
        protocol=Protocol(cfg)
        import unittest
        suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_contract.py')
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        assert result.wasSuccessful() and result.testsRun==9
        from transformers import AutoTokenizer
        tokenizers={};gates={}
        for arm in MODELS:
            with heartbeat('tokenizer_'+arm['arm']):
                tok=AutoTokenizer.from_pretrained(arm['checkpoint'],revision=arm['revision'])
                tokenizers[arm['arm']]=tok
                synthetic=[{'role':'user','content':'Synthetic contract test'},
                    {'role':'assistant','content':'','tool_calls':[{'type':'function','function':
                        {'name':'synthetic.echo','arguments':{'text':'hello','amount':12}}}]},
                    {'role':'tool','content':'{"ok":true,"id":"synthetic_42"}'}]
                rendered=tok.apply_chat_template(synthetic,tokenize=False,add_generation_prompt=True,enable_thinking=False)
                assert '<tool_response>' in rendered and 'synthetic_42' in rendered
                if arm['arm']=='qwen35':
                    assert '<function=synthetic.echo>' in rendered and '<parameter=amount>' in rendered
                    assert rendered.endswith('<think>\n\n</think>\n\n')
                else:assert '"name": "synthetic.echo"' in rendered
            counts={};input_hashes={}
            for sid in IDS:
                sample=copy.deepcopy(samples[sid]);sample.label=None
                assert sample.audio_text is not None
                assert all(t.audio_text is not None for t in sample.history if t.role=='user')
                tools=catalog_tools_for_sample(catalog,sample);capture=[]
                def check(messages,tools):capture.append(messages);return None
                class Empty:
                    def submission_line(self):return {'tool_calls':[]}
                AgentLoop(cfg,tools).run(sample,sample.audio_text,Empty(),check,protocol=protocol)
                messages=capture[0]
                wire=tok.apply_chat_template(messages,tools=function_definitions(tools),tokenize=False,
                                            add_generation_prompt=True,enable_thinking=False)
                n=len(tok.encode(wire,add_special_tokens=False));assert n+512<=16384
                assert '<tools>' in wire and sample.audio_text in wire
                for t in sample.history:
                    if t.role=='user':assert t.audio_text in wire
                input_hashes[sid]=hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                counts[sid]=n
            gates[arm['arm']]={'tokens':counts,'initial_message_hashes':input_hashes,
                              'template_sha256':hashlib.sha256(tok.chat_template.encode()).hexdigest()}
        assert gates['qwen3']['initial_message_hashes']==gates['qwen35']['initial_message_hashes']
        write(OUT/'preweight_gates.json',gates)
        print('PREWEIGHT_GATES_PASS',gates,flush=True)
        if os.environ.get('PILOT_CPU_ONLY')=='1':
            summary['status']='CPU_GATES_PASSED';write(OUT/'summary.json',summary);return
        import torch
        from transformers import AutoModelForCausalLM,set_seed,StoppingCriteria,StoppingCriteriaList
        from transformers.integrations import sdpa_attention
        from torch.nn.attention import SDPBackend,sdpa_kernel
        assert torch.cuda.is_available() and torch.cuda.device_count()==2
        summary['hardware']=[{'name':torch.cuda.get_device_name(i),
            'bytes':torch.cuda.get_device_properties(i).total_memory} for i in range(2)]
        summary['packages']={n:importlib.metadata.version(n) for n in
                             ['torch','transformers','accelerate','huggingface-hub']}
        @contextmanager
        def efficient():
            if not hasattr(sdpa_attention,'use_gqa_in_sdpa'):
                raise RuntimeError('Pinned SDPA helper changed; refuse quadratic math fallback')
            old=sdpa_attention.use_gqa_in_sdpa
            sdpa_attention.use_gqa_in_sdpa=lambda *a,**k:False
            try:
                with sdpa_kernel(SDPBackend.EFFICIENT_ATTENTION):yield
            finally:sdpa_attention.use_gqa_in_sdpa=old
        # Check supported T4 attention shape and tiny parity before weight download.
        with torch.no_grad():
            q=torch.randn(1,16,64,256,device='cuda:0',dtype=torch.float16)
            k=torch.randn(1,4,64,256,device='cuda:0',dtype=torch.float16);v=torch.randn_like(k)
            with sdpa_kernel(SDPBackend.EFFICIENT_ATTENTION):
                got=torch.nn.functional.scaled_dot_product_attention(q,k.repeat_interleave(4,1),v.repeat_interleave(4,1),is_causal=True)
            with sdpa_kernel(SDPBackend.MATH):
                ref=torch.nn.functional.scaled_dot_product_attention(q,k,v,is_causal=True,enable_gqa=True)
            torch.testing.assert_close(got,ref,atol=3e-3,rtol=3e-3)
            del q,k,v,got,ref
        class Deadline(StoppingCriteria):
            def __init__(self,deadline):self.deadline=deadline;self.hit=False
            def __call__(self,*a,**k):self.hit=time.monotonic()>self.deadline;return self.hit
        from huggingface_hub import snapshot_download
        for arm in MODELS:
            name=arm['arm'];folder=OUT/name;folder.mkdir(exist_ok=True)
            set_seed(42);tok=tokenizers[name]
            with heartbeat('download_'+name):
                model_path=snapshot_download(arm['checkpoint'],revision=arm['revision'],max_workers=4,
                    allow_patterns=['*.json','*.jinja','*.safetensors','*.model','merges.txt','vocab.json'],
                    cache_dir=str(WORK/'hf_cache'))
            with heartbeat('load_'+name):
                model,loading=AutoModelForCausalLM.from_pretrained(model_path,dtype=torch.float16,
                    attn_implementation='sdpa',device_map='balanced',max_memory={0:'9GiB',1:'9GiB'},
                    local_files_only=True,output_loading_info=True)
                write(folder/'loading_info.json',loading)
                if loading.get('missing_keys') or loading.get('mismatched_keys') or loading.get('error_msgs'):
                    raise RuntimeError('Incomplete checkpoint load; no random-init comparison')
                model.eval()
            placement={str(k):str(v) for k,v in getattr(model,'hf_device_map',{}).items()}
            assert placement and not any(v in ('cpu','disk') for v in placement.values())
            write(folder/'model_identity.json',{'arm':arm,'class':type(model).__name__,
                'parameter_count_loaded':sum(p.numel() for p in model.parameters()),'placement':placement,
                'generation_config':model.generation_config.to_dict()})
            device=next(model.parameters()).device
            results=[];classes=[]
            for sid in IDS:
                sample=copy.deepcopy(samples[sid]);label_sample=copy.deepcopy(sample);sample.label=None
                tools=catalog_tools_for_sample(catalog,sample);env=ZaicEnv(root,'train',sid)
                record={'id':sid,'arm':name,'generations':[],'executions':[],'validation_rejected':[]}
                started=time.monotonic();sample_deadline=started+240
                original_call,original_validate=env.call,env.validate
                def observe_call(n,a):
                    res=original_call(n,a);record['executions'].append({'name':n,'arguments':copy.deepcopy(a),'result':res});return res
                def observe_validate(n,a):
                    res=original_validate(n,a)
                    if not res.get('ok'):record['validation_rejected'].append({'name':n,'arguments':copy.deepcopy(a),'result':res})
                    return res
                env.call,env.validate=observe_call,observe_validate
                def generate(messages,tools):
                    if time.monotonic()>=sample_deadline:raise TimeoutError('Sample soft budget exhausted')
                    wire=tok.apply_chat_template(messages,tools=function_definitions(tools),tokenize=False,
                                                add_generation_prompt=True,enable_thinking=False)
                    ids=tok(wire,return_tensors='pt',add_special_tokens=False).to(device)
                    size=ids['input_ids'].shape[1]
                    if size+512>16384:raise ValueError('Context budget exceeded; no truncation')
                    deadline=Deadline(min(sample_deadline,time.monotonic()+90))
                    tick=time.monotonic()
                    with heartbeat(name+'_'+sid+'_generation_'+str(len(record['generations'])+1)),torch.inference_mode(),efficient():
                        out=model.generate(**ids,max_new_tokens=512,do_sample=False,
                            eos_token_id=tok.convert_tokens_to_ids('<|im_end|>'),
                            pad_token_id=tok.pad_token_id or tok.convert_tokens_to_ids('<|im_end|>'),
                            stopping_criteria=StoppingCriteriaList([deadline]))
                    tokens=out[0][size:];raw=tok.decode(tokens,skip_special_tokens=True)
                    diagnostic={'raw':raw,'messages':messages,'prompt_tokens':size,
                        'output_tokens':len(tokens),'seconds':time.monotonic()-tick,'deadline_hit':deadline.hit,
                        'token_limit_hit':len(tokens)>=512,
                        'message_sha256':hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
                    try:
                        if deadline.hit:raise TimeoutError('Generation deadline reached')
                        if len(tokens)>=512:raise ValueError('Output token cap reached; not a clean stop')
                        if name=='qwen35':proposal,meta=parse_q35(raw,tools)
                        else:proposal,meta=parse_native(raw,reject_pseudo_calls=True)
                        diagnostic.update(parser=meta,proposal=proposal)
                    except ValueError as exc:
                        proposal={'name':'__invalid__','arguments':{'native_format_error':str(exc)}}
                        diagnostic.update(parser_error=str(exc),proposal=proposal)
                    finally:
                        record['generations'].append(diagnostic);write(folder/(sid+'.json'),record)
                    return proposal
                try:
                    submission=AgentLoop(cfg,tools).run(sample,sample.audio_text,env,generate,protocol=protocol)
                    record['status']='COMPLETE'
                except Exception as exc:
                    record['status']='ERROR';record['error']=repr(exc);submission=env.submission_line()
                record.update(submission=submission,seconds=time.monotonic()-started)
                # Gold is accessed only AFTER the agent has returned.
                gold=ZaicEnv(root,'train',sid)
                for call in label_sample.label['tool_calls']:gold.call(call['name'],call['arguments'])
                metric=score_sample(submission,label_sample,gold.state_hash(),fuzzy_params(catalog))
                replay=ZaicEnv(root,'train',sid)
                for call in submission['tool_calls']:replay.call(call['name'],call['arguments'])
                assert replay.submission_line()==submission
                record['metric']=metric;record['replay_verified']=True
                write(folder/(sid+'.json'),record);results.append(metric);classes.append(label_sample.label_class())
                print('SAMPLE_DONE',name,sid,record['status'],metric,'seconds',round(record['seconds'],1),flush=True)
            summary['arms'][name]=summarise(results,classes)
            summary['arms'][name]['all_samples_complete']=all(json.loads((folder/(sid+'.json')).read_text())['status']=='COMPLETE' for sid in IDS)
            write(OUT/'summary.json',summary)
            del model;gc.collect();torch.cuda.empty_cache()
        summary['status']='COMPLETE' if all(v['all_samples_complete'] for v in summary['arms'].values()) else 'COMPLETED_WITH_ERRORS'
    except Exception:
        summary['status']='FAILED';summary['error']=traceback.format_exc();print(summary['error'],flush=True)
        raise
    finally:
        write(OUT/'summary.json',summary)


if __name__=='__main__':main()
