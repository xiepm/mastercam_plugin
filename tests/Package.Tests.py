"""Read-only checks of payload dependencies and public release contents."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parents[1]
payload = root / "payload"
manifest = json.loads((root / "catalog/package.json").read_text("utf-8-sig"))
files = {p.relative_to(payload).as_posix().lower(): p for p in payload.rglob("*") if p.is_file()}
checks = []
original = json.loads((root / 'validation/xplus-provenance.json').read_text('utf-8-sig'))
# Exact vendor source/PDB paths inspected in these unmodified original files.
vendor_debug_paths = {
    'chainit.dll', 'fixturesetup.dll', 'level2stlres.dll',
    'mergefixtureres.dll', 'svgimageres.dll', 'tpsketcher.dll',
}


def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)


check("Payload count matches manifest", len(files) == len(manifest["files"]))
for vendor_file in original['files']:
    check('Original X+ remains byte-identical ' + vendor_file['path'], hashlib.sha256(files[vendor_file['path'].lower()].read_bytes()).hexdigest().upper() == vendor_file['sha256'])
for item in manifest["files"]:
    data = files[item["path"].lower()].read_bytes()
    check("SHA256 " + item["path"], hashlib.sha256(data).hexdigest().upper() == item["sha256"])
for name, path in files.items():
    if path.suffix == ".ft":
        text = path.read_text("utf-8-sig")
        target = re.search(r'FUNC_DLL\s+"([^"]+)"', text, re.I)
        check("FT function DLL " + name, bool(target) and target[1].replace("\\", "/").lower() in files)
        resource = re.search(r'RES_DLL\s+"([^"]+)"\s*,\s*"([^"]+)"', text, re.I)
        if resource:
            check("FT resource DLL " + name, (resource[2] + "/" + resource[1]).replace("\\", "/").lower() in files)
        else:
            resource = re.search(r'RES_DLL\s+"([^"]+)"', text, re.I)
            if resource:
                check("FT native resource DLL " + name, resource[1].replace("\\", "/").lower() in files)
        if name == 'chooks/hsmrebuild2027.ft':
            check('HSM managed FT resource contract', 'dnRES_NAME "Workshop2027.NETHook"' in text and bool(resource))
    data = path.read_bytes()
    for marker in ("C:\\Users\\", "D:\\Users\\", "\\NXTEST\\", "IPCServer.dll", "license.CimcoLicense", "PRIVATE KEY"):
        if marker == 'C:\\Users\\' and name.startswith('chooks/x+/') and path.name.lower() in vendor_debug_paths:
            occurrences = re.findall(rb'[ -~]*C:\\Users\\[ -~]*', data)
            check('Only original vendor source/debug paths ' + name, bool(occurrences) and all(s.startswith(b'C:\\Users\\GMCCS\\source\\repos\\MC2027\\') and s.endswith((b'.pdb', b'.cpp')) for s in occurrences) and marker.encode('utf-16-le') not in data)
            continue
        check("No development data " + name + " / " + marker, marker.encode() not in data and marker.encode("utf-16-le") not in data)
blocked = {"nethook3_0.dll", "mccore.dll", "mcgeomsld.dll", "pskernel.dll", "hsm.dll", "htkernel.dll"}
check("No Mastercam SDK, kernel or HSM vendor binaries", not any(p.name.lower() in blocked for p in files.values()))
modules = json.loads((root / "catalog/modules.json").read_text("utf-8-sig"))
check("Module count matches manifest", len(modules) == manifest["moduleCount"])
apps = {}
for path in files.values():
    if path.suffix.lower() != '.ft':
        continue
    ft = path.read_text('utf-8-sig')
    app = re.search(r'APPLICATION\s+"([^"]+)"', ft)
    if app:
        apps.setdefault(app[1], set()).update(re.findall(r'FUNCTION\s+(?:NET|CPP)\s+"([^"]+)"', ft))
workshop = '\n'.join(p.read_text('utf-8-sig') for p in (root / 'src/Workshop').glob('*.cs'))
for app, command in re.findall(r'Forward\("([^"]+)","([^"]+)"\)', workshop):
    check('Workshop route ' + app + '.' + command, command in apps.get(app, set()))
for module in modules:
    check("Module files resolve " + module["id"], all(f.lower() in files for f in module["files"]))
check("Frozen Porsche business binary", manifest["files"][0] is not None and hashlib.sha256((payload / "chooks/PorscheAdvanced2027/PorscheAdvanced2027.dll").read_bytes()).hexdigest().upper() == "DA8E4F21100013EB766CB5C62DF47768A039E59A8CB5E986FB2D7A2FA2F231CE")
check("Frozen OperationTools business binary", hashlib.sha256((payload / "chooks/OperationTools2027/OperationTools2027.dll").read_bytes()).hexdigest().upper() == "26074B7E8EEBEE2C6B2CA52D1ED9744F42DDC894D245B86B4610E71C656A4B50")
report = {"date": "2026-10-28", "passed": True, "checks": len(checks), "ftFiles": sum(p.suffix == ".ft" for p in files.values()), "payloadFiles": len(files), "categories": ["SHA256", "FT DLL and resource dependencies", "Development data exclusion", "Vendor binary exclusion", "Module inventory", "Frozen business binaries"]}
(root / "validation/package-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
print(json.dumps(report))
