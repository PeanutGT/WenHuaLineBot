import urllib.request
import json
import tarfile
import io
import os

print("Fetching latest Zrok release info...")
req = urllib.request.urlopen('https://api.github.com/repos/openziti/zrok/releases/latest')
data = json.loads(req.read().decode('utf-8'))

url = None
for asset in data['assets']:
    if 'windows_amd64.tar.gz' in asset['name']:
        url = asset['browser_download_url']
        break

if url:
    print(f"Downloading Zrok from {url} ...")
    with urllib.request.urlopen(url) as r:
        with tarfile.open(fileobj=io.BytesIO(r.read()), mode='r:gz') as tar:
            tar.extractall('dist/SmartSchoolBot')
    print("Zrok downloaded and extracted to dist/SmartSchoolBot")
else:
    print("Could not find Windows AMD64 release.")
