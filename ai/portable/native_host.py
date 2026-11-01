"""Launch the configured desktop host; the caller owns its process lifetime."""
import csv,io,subprocess
from pathlib import Path
from .common import scoped

def launch(c,file_path=None):
    found=subprocess.run(['tasklist','/FI','IMAGENAME eq Mastercam.exe','/FO','CSV','/NH'],capture_output=True,text=True,encoding='mbcs',errors='replace',timeout=10)
    if any(row and row[0].lower()=='mastercam.exe' for row in csv.reader(io.StringIO(found.stdout))):
        raise RuntimeError('Mastercam already running; preserve its document and inspect before using File/Open')
    executable=Path(c['mastercam_root'])/'Mastercam.exe'
    if not executable.is_file():raise FileNotFoundError(executable)
    args=[str(executable),'/M3']
    if file_path:
        p=scoped(file_path,c,exists=True)
        if p.suffix.lower() not in {'.dxf','.step','.stp','.mcam'}:raise ValueError('Unsupported format')
        args.append(str(p))
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=1
    process=subprocess.Popen(args,cwd=str(executable.parent),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,startupinfo=startup)
    return {'started':True,'pid':process.pid,'ready':False,'next':'Wait for startup, then mastercam_inspect'}
