"""Compile NET-Script against installed API29 without executing its contents."""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portable.common import ROOT, config, sha

def runtime_directory():
    dotnet=shutil.which('dotnet')
    if not dotnet:
        candidate=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'dotnet/dotnet.exe'
        if candidate.is_file():dotnet=str(candidate)
    if not dotnet:raise ValueError('.NET 10 Windows Desktop runtime is required')
    text=subprocess.check_output([dotnet,'--list-runtimes'],text=True)
    matches=[]
    for line in text.splitlines():
        if line.startswith('Microsoft.WindowsDesktop.App 10.'):
            name,version,base=line.split(' ',2)
            if '-' not in version:matches.append((tuple(map(int,version.split('.'))),Path(base.strip('[]'))/version))
    if not matches:raise ValueError('.NET 10 Windows Desktop runtime is required')
    return dotnet,max(matches)[1]

def json_assembly():
    dotnet,desktop=runtime_directory()
    root=desktop.parent.parent/'Microsoft.NETCore.App'
    matches=sorted((p for p in root.glob('10.*') if '-' not in p.name and (p/'System.Text.Json.dll').is_file()),key=lambda p:tuple(map(int,p.name.split('.'))))
    if not matches:raise ValueError('System.Text.Json for .NET 10 is missing')
    return matches[-1]/'System.Text.Json.dll'

def compile_script(path,c):
    dotnet,desktop=runtime_directory();source=ROOT/'ai/compiler/Mc2027Compile.cs'
    build=Path(c['workspace'])/'compiler'/sha(source)[:16];build.mkdir(parents=True,exist_ok=True)
    exe=build/'Mc2027Compile.exe'
    if not exe.exists():
        csc=Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        subprocess.run([str(csc),'/nologo','/target:exe','/out:'+str(exe),str(source)],check=True,capture_output=True,text=True)
        exe.with_suffix('.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':'net10.0','framework':{'name':'Microsoft.WindowsDesktop.App','version':desktop.name},'rollForward':'LatestPatch'}}),encoding='utf-8')
    result=subprocess.run([dotnet,str(exe),str(Path(path).resolve()),c['mastercam_root']],capture_output=True,text=True)
    print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr)
    return result.returncode

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config');p.add_argument('--script');p.add_argument('--json-assembly',action='store_true');a=p.parse_args()
    if a.json_assembly:print(json_assembly().as_posix());return 0
    if not a.script:p.error('--script is required')
    return compile_script(a.script,config(a.config))
if __name__=='__main__':raise SystemExit(main())
