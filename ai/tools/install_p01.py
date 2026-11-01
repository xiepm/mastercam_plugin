"""Install the pinned headless P01 environment inside Linux/WSL, outside the repo."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prefix',type=Path,default=Path.home()/'.local/share/mastercam-agent/p01-occt751')
    p.add_argument('--micromamba',type=Path,default=Path(shutil.which('micromamba') or Path.home()/'.local/bin/micromamba'))
    a=p.parse_args();prefix=a.prefix.resolve();mamba=a.micromamba.resolve()
    if sys.platform!='linux':p.error('Run this installer inside Linux/WSL')
    if prefix.is_relative_to(ROOT):p.error('The dependency environment must be outside the source repository')
    if not mamba.is_file():p.error('Install micromamba, or supply --micromamba with its executable path')
    if prefix.exists():p.error('Choose a fresh prefix; existing environments are preserved')
    manifest=ROOT/'ai/environments/p01-linux64-packages.json'
    packages=json.loads(manifest.read_text())['packages']
    subprocess.run([str(mamba),'create','--yes','--prefix',str(prefix),'--file',str(ROOT/'ai/environments/p01-linux64.explicit.txt')],check=True)
    installed={x['name']:x for path in (prefix/'conda-meta').glob('*.json') for x in [json.loads(path.read_text())]}
    for expected in packages:
        actual=installed[expected['name']]
        for key in ('version','build','sha256'):
            if actual.get(key)!=expected[key]:raise RuntimeError('Package identity mismatch: '+expected['name']+'/'+key)
    python=prefix/'bin/python'
    subprocess.run([str(python),'-m','pip','install','--no-deps','--require-hashes','-r',str(ROOT/'ai/environments/p01-extra-linux.lock.txt')],check=True)
    code='import json,sys,importlib.metadata as m,OCC,occwl,manifold3d;print(json.dumps(dict(python=sys.version.split()[0],occt=OCC.VERSION,occwl=m.version("occwl"),manifold3d=m.version("manifold3d"))))'
    versions=json.loads(subprocess.check_output([str(python),'-c',code],text=True))
    if versions['occt']!='7.5.1' or versions['occwl']!='2.0.2':raise RuntimeError('Face namespace environment differs')
    report={'passed':True,'packages':len(packages),'versions':versions,'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'model_inference_installed':False,'native_cam_tested':False}
    (prefix/'mastercam-p01-install.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'python':str(python),**report}))

if __name__=='__main__':main()
