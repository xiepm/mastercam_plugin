"""Explicit local-only transfer of authorized references; never uploads data."""
import json,stat,zipfile
from pathlib import Path,PurePosixPath,PureWindowsPath
from .common import ROOT,load,sha,write_new
from .planning import compile_index
from jsonschema import Draft202012Validator


def validate(manifest):
    Draft202012Validator(load(ROOT/'ai/schemas/private-reference-bundle.schema.json')).validate(manifest)


def safe(root,name):
    if '\\' in name or ':' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or PureWindowsPath(name).is_reserved():
        raise ValueError('Unsafe bundle path: '+name)
    target=(root/name).resolve()
    if not target.is_relative_to(root.resolve()):raise ValueError('Bundle path escapes destination')
    return target


def export_bundle(knowledge_root,output):
    root=Path(knowledge_root).resolve();output=Path(output).resolve()
    if output.is_relative_to(ROOT):raise ValueError('Private knowledge bundle must stay outside repository')
    index=compile_index(root/'catalog.json',root/'merged/merge_plan.json')
    catalog=load(root/'catalog.json');files={'catalog.json','merged/merge_plan.json'}
    for case in catalog['cases']:
        library=safe(root,case['library']);lib=load(library);case_root=(library.parent/lib['evidence_root']).resolve()
        files.update([case['library'],case['report']])
        for evidence in lib['evidence']:
            files.add((case_root/evidence['path']).resolve().relative_to(root).as_posix())
    for name in ['README.md','merged/模板库总览.md','merged/冲突清单.md','merged/缺失清单.md']:
        if (root/name).is_file():files.add(name)
    manifest=dict(schema_version='mastercam.private-reference-bundle/1',private_data=True,
                  catalog_sha256=sha(root/'catalog.json'),case_count=index['case_count'],record_count=index['record_count'],
                  files=[dict(path=name,sha256=sha(safe(root,name))) for name in sorted(files)])
    validate(manifest)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('bundle-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        for entry in manifest['files']:
            path=safe(root,entry['path'])
            if sha(path)!=entry['sha256']:raise ValueError('Source changed during export')
            z.write(path,entry['path'])
    (output.with_suffix(output.suffix+'.sha256')).write_text(sha(output)+'\n','ascii')
    return dict(path=str(output),sha256=sha(output),cases=index['case_count'],records=index['record_count'],private_data=True)


def import_bundle(archive,destination,expected_sha256):
    archive=Path(archive).resolve();dest=Path(destination).resolve()
    if dest.is_relative_to(ROOT):raise ValueError('Private knowledge must stay outside repository')
    if dest.exists():raise ValueError('Destination exists; import into a fresh directory')
    if sha(archive)!=expected_sha256.lower():raise ValueError('Bundle SHA256 mismatch')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)>10000:raise ValueError('Duplicate or excessive bundle entries')
        if sum(i.file_size for i in z.infolist())>2*1024**3:raise ValueError('Bundle exceeds 2 GiB limit')
        for item in z.infolist():
            safe(dest,item.filename)
            if item.is_dir() or stat.S_ISLNK(item.external_attr>>16):raise ValueError('Only regular file entries supported')
        manifest=json.loads(z.read('bundle-manifest.json'))
        validate(manifest)
        if manifest.get('schema_version')!='mastercam.private-reference-bundle/1':raise ValueError('Unknown bundle version')
        listed={r['path']:r['sha256'] for r in manifest['files']}
        if len(listed)!=len(manifest['files']) or set(names)!=(set(listed)|{'bundle-manifest.json'}):raise ValueError('Bundle inventory mismatch')
        import hashlib
        for name,digest in listed.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise ValueError('Bundle entry hash mismatch: '+name)
        dest.mkdir(parents=True)
        for name in names:
            target=safe(dest,name);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(z.read(name))
    index=compile_index(dest/'catalog.json',dest/'merged/merge_plan.json')
    if sha(dest/'catalog.json')!=manifest['catalog_sha256']:raise ValueError('Catalog binding mismatch')
    if any(index[key]!=manifest[key] for key in ['case_count','record_count']):raise ValueError('Bundle count mismatch')
    write_new(dest/'merged/index.json',index)
    return dict(knowledge_root=str(dest),cases=index['case_count'],records=index['record_count'],verified=True)
