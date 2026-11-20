"""Download official build inputs into this project only (no system installation)."""
import concurrent.futures
import hashlib
from pathlib import Path
import urllib.request
import subprocess
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).parent / '.tools'
ROOT.mkdir(exist_ok=True)

def fetch(url, target):
    if not target.exists():
        print('Downloading', url, flush=True)
        temp = target.with_suffix('.partial')
        subprocess.run(['curl.exe','--fail','--location','--retry','2','--connect-timeout','15','--max-time','600','--silent','--show-error','--output',str(temp),url], check=True)
        temp.replace(target)
    return target

def sdk(package, destination):
    xml_path = fetch('https://dl.google.com/android/repository/repository2-3.xml', ROOT/'repository.xml')
    tree = ET.parse(xml_path)
    item = next(x for x in tree.getroot() if x.tag.endswith('remotePackage') and x.attrib.get('path') == package)
    archive = next(a for a in item.findall('./archives/archive') if a.findtext('host-os') in ('windows', None))
    url = archive.findtext('./complete/url')
    path = fetch('https://dl.google.com/android/repository/'+url, ROOT/(destination+'.zip'))
    import hashlib
    checksum = archive.find('./complete/checksum')
    algorithm = checksum.attrib.get('type', 'sha1')
    if hashlib.new(algorithm, path.read_bytes()).hexdigest().lower() != checksum.text.lower():
        raise RuntimeError('SDK archive checksum mismatch')
    with zipfile.ZipFile(path) as z:
        z.extractall(ROOT/destination)
    print('Ready',destination,flush=True)

def jdk():
    base = 'https://aka.ms/download-jdk/microsoft-jdk-17.0.21.0.2-windows-x64.zip'
    path = fetch(base, ROOT/'jdk.zip')
    checksum = fetch(base+'.sha256sum.txt', ROOT/'jdk.sha256sum.txt').read_text().split()[0]
    if hashlib.sha256(path.read_bytes()).hexdigest().lower() != checksum.lower():
        raise RuntimeError('JDK archive checksum mismatch')
    with zipfile.ZipFile(path) as z:
        z.extractall(ROOT/'jdk')
    print('Ready JDK',flush=True)

if __name__ == '__main__':
    # Fetch repository once before independent archive downloads.
    fetch('https://dl.google.com/android/repository/repository2-3.xml', ROOT/'repository.xml')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(jdk),pool.submit(sdk,'build-tools;35.0.0','build-tools'),pool.submit(sdk,'platforms;android-35','platform')]
        for f in futures:
            f.result()
