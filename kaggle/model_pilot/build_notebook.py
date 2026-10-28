"""Embed the audited experiment; no credentials or friend's private files."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
DEST=HERE.parents[2]/'artifacts'/'lifemate-model-pilot'


def build(cpu=False):
    files={n:(HERE/n).read_text(encoding='utf-8') for n in ['contract.py','test_contract.py','runner.py']}
    launcher='''import os,sys,json,time,subprocess,signal,threading
from pathlib import Path
root=Path('/kaggle/temp/model_pilot_code');root.mkdir(parents=True,exist_ok=True)
output=Path('/kaggle/working/model_pilot');output.mkdir(parents=True,exist_ok=True)
os.environ.update(USE_TF='0',USE_FLAX='0',HF_HUB_DISABLE_XET='1',HF_HUB_DOWNLOAD_TIMEOUT='60',TOKENIZERS_PARALLELISM='false')
FILES=__FILES__
for name,content in FILES.items():(root/name).write_text(content,encoding='utf-8')
def run(command,label,limit):
    log=output/(label+'.log');started=time.monotonic()
    with open(log,'w',encoding='utf-8') as stream:
        p=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while True:
                try:
                    code=p.wait(timeout=15);break
                except subprocess.TimeoutExpired:
                    print('PROGRESS',label,round(time.monotonic()-started,1),'seconds','log_bytes',log.stat().st_size,flush=True)
                    tail=log.read_text(encoding='utf-8',errors='replace').splitlines()[-2:]
                    print('\\n'.join(tail),flush=True)
                    if time.monotonic()-started>limit:raise TimeoutError(label+' wall-clock limit')
        except BaseException:
            os.killpg(p.pid,signal.SIGKILL);p.wait();raise
    if code:
        print(log.read_text(encoding='utf-8',errors='replace')[-8000:],flush=True)
        raise RuntimeError(label+' failed: '+str(code))
run([sys.executable,'-m','pip','uninstall','-y','torchao','torchvision'],'remove_unused_optional_packages',120)
run([sys.executable,'-m','pip','install','--no-cache-dir','-q',
     'transformers==5.20.2','accelerate==1.15.0','huggingface-hub==2.3.0',
     'jsonschema==4.25.1','rapidfuzz==3.14.3'],'dependencies',600)
__CPU__
run([sys.executable,'-u',str(root/'runner.py')],'pilot',2400)
print((output/'summary.json').read_text(),flush=True)
'''.replace('__FILES__',repr(files)).replace('__CPU__',"os.environ['PILOT_CPU_ONLY']='1'" if cpu else "os.environ.pop('PILOT_CPU_ONLY',None)")
    metadata={'id':'khanhss/lifemate-native-contract-canary-20261028' if cpu else 'khanhss/lifemate-smoke-dev5-20261027',
        'title':'LifeMate Native Contract Canary 20261028' if cpu else 'LifeMate Smoke Dev5 20261027',
        'code_file':'run.ipynb','language':'python','kernel_type':'notebook','is_private':True,
        'enable_gpu':not cpu,'enable_internet':True,
        'dataset_sources':['khanhss/lifemate-runtime-inputs-20261028/1','khanhss/lifemate-pseudo-source-a472006/1'],
        'competition_sources':[],'kernel_sources':[],'model_sources':[]}
    if not cpu:metadata['machine_shape']='NvidiaTeslaT4'
    nb={'cells':[{'cell_type':'markdown','metadata':{},'source':'# LifeMate gold-current + gold-history model pilot\n8 selected dev samples; no ASR, no training, no held-out. Not a representative benchmark.'},
                 {'cell_type':'code','metadata':{},'source':launcher,'execution_count':None,'outputs':[]}],
        'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}},
        'nbformat':4,'nbformat_minor':4}
    compile(launcher,'notebook','exec')
    for n,s in files.items():compile(s,n,'exec')
    folder=DEST/('cpu-launch' if cpu else 'gpu-launch');folder.mkdir(parents=True,exist_ok=True)
    (folder/'run.ipynb').write_text(json.dumps(nb,ensure_ascii=True),encoding='utf-8')
    (folder/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    (DEST/'source_hashes.json').write_text(json.dumps({n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()},indent=2),encoding='utf-8')
    print(folder)


if __name__=='__main__':build(cpu=True);build(cpu=False)
