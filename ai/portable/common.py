"""Shared local configuration; no machine-specific paths or client credentials."""
from __future__ import annotations
import hashlib, json, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = '2027.11.01.2'

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')

def config(path=None):
    path = path or os.environ.get('MC_BRIDGE_CONFIG') or os.environ.get('MC_PLUGIN_AI_CONFIG')
    if not path:
        raise ValueError('Run Install-AI.cmd first, or provide --config.')
    c = load(path)
    for key in ('mastercam_root', 'workspace'):
        if not Path(c.get(key, '')).is_absolute():
            raise ValueError(key + ' must be an absolute local path')
        c[key] = str(Path(c[key]).resolve())
    if Path(c['workspace']).is_relative_to(ROOT):
        raise ValueError('Private workspace must be outside the distributable repository')
    c['config_path'] = str(Path(path).resolve())
    return c

def scoped(path, c, *, exists=False):
    p = Path(path).resolve()
    if not p.is_relative_to(Path(c['workspace']).resolve()):
        raise ValueError('Path is outside the configured workspace')
    if exists and not p.is_file():
        raise FileNotFoundError(p)
    return p

def token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise ValueError('ID must contain 1-80 ASCII letters, digits, hyphens or underscores')
    return value
