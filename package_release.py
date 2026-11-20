from pathlib import Path
import hashlib
import shutil
import zipfile
import sys

sys.stdout.reconfigure(encoding='utf-8')

root=Path(__file__).resolve().parent
dist=root/'dist'
for name in ('README.md','快速开始.txt','TESTING.md'):
    shutil.copyfile(root/name,dist/name)
artifacts=['LanRemote-Windows.exe','LanRemote-Android.apk','快速开始.txt','README.md','TESTING.md']
checksums=[]
for name in artifacts:
    path=dist/name
    checksums.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+name)
(dist/'SHA256SUMS.txt').write_text('\n'.join(checksums)+'\n',encoding='utf-8')
with zipfile.ZipFile(dist/'LanRemote-0.2.0-安装包.zip','w',zipfile.ZIP_DEFLATED) as z:
    for name in artifacts+['SHA256SUMS.txt']:
        z.write(dist/name,name)
with zipfile.ZipFile(dist/'LanRemote-0.2.0-源码.zip','w',zipfile.ZIP_DEFLATED) as z:
    for path in root.rglob('*'):
        rel=path.relative_to(root)
        if path.name.startswith('firewall-') or path.name=='repair-this-pc.ps1':
            continue
        if any(part in {'.deps','.tools','build','dist','__pycache__','.gradle'} for part in rel.parts):
            continue
        if path.is_file() and path.suffix not in {'.spec','.pyc','.jks'}:
            z.write(path,rel)
for path in dist.iterdir():
    if path.is_file():
        print(path.name, path.stat().st_size)
for name in ('LanRemote-0.2.0-安装包.zip','LanRemote-0.2.0-源码.zip'):
    with zipfile.ZipFile(dist/name) as z:
        assert z.testzip() is None
print('Archive integrity: OK')
