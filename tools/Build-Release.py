"""Create a deterministic, allowlisted release archive. Python standard library only."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "catalog/package.json").read_text("utf-8-sig"))["version"]
NAME = f"Mastercam2027-PluginSuite-{VERSION}"
TOP_FILES = {"README.md", "CHANGELOG.md", "Manage.ps1", "Install.cmd", "Uninstall.cmd", "Verify.cmd"}
DIRECTORIES = {"payload", "catalog", "docs", "scripts", "src", "tools", "tests", "validation"}


def build():
    files = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if len(rel.parts) == 1 and p.name in TOP_FILES or len(rel.parts) > 1 and rel.parts[0] in DIRECTORIES:
            if any(x in rel.parts for x in ("__pycache__", ".git", "backups", ".test-work")):
                continue
            files.append(p)
    files.sort(key=lambda x: x.relative_to(ROOT).as_posix())
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    archive = output / f"{NAME}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            name = NAME + "/" + p.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(name, (2026, 10, 28, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, p.read_bytes())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(files)
        for p in files:
            assert z.read(NAME + "/" + p.relative_to(ROOT).as_posix()) == p.read_bytes()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(json.dumps({"archive": str(archive), "files": len(files), "bytes": archive.stat().st_size, "sha256": digest}))


if __name__ == "__main__":
    build()
