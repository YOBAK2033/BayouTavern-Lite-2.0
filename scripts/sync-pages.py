"""Build Pages only from a complete, checksum-verified latest stable Release."""
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

REPOSITORY = 'YOBAK2033/BayouTavern-Lite-2.0'
ROOT = f'https://github.com/{REPOSITORY}/releases/download/'

def get(url, limit, token=False):
    headers = {'User-Agent': 'BayouTavern-Lite-Pages', 'Accept': 'application/vnd.github+json' if token else '*/*'}
    if token and os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Release asset exceeds allowed size')
    return data

def prepare(release, fetch, output):
    match = re.fullmatch(r'v(2)\.(\d{1,2})\.(\d{1,2})', release['tag_name'])
    if not match or release.get('draft') or release.get('prerelease'):
        raise ValueError('Expected a stable Lite 2.x.x release')
    version = release['tag_name'][1:]
    names = {'web': f'BayouTavern-Lite-{version}.html', 'android': f'BayouTavern-Lite-{version}-android.apk'}
    assets = {asset['name']: asset for asset in release['assets'] if asset.get('state') == 'uploaded'}
    if any(name not in assets for name in [*names.values(), 'SHA256SUMS.txt']):
        raise ValueError('Upload HTML, APK and SHA256SUMS.txt before publishing')
    def url(asset):
        expected = ROOT + release['tag_name'] + '/' + asset['name']
        if asset['browser_download_url'] != expected:
            raise ValueError('Unexpected asset URL')
        return expected
    sums = fetch(url(assets['SHA256SUMS.txt']), 65536).decode('utf-8-sig')
    hashes = {}
    for line in sums.splitlines():
        item = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?([^/\\]+)', line.strip())
        if item:
            if item[2] in hashes:
                raise ValueError('Duplicate checksum entry')
            hashes[item[2]] = item[1].lower()
    feed = {'version': version, 'versionCode': int(match[1])*10000+int(match[2])*100+int(match[3]), 'applicationId': 'studio.bayoucard.lite', 'publishedAt': release['published_at'], 'notes': (release.get('body') or '')[:12000]}
    html = None
    for kind, name in names.items():
        asset = assets[name]
        digest = hashes.get(name)
        if not digest or asset.get('digest') != 'sha256:' + digest or not 0 < asset['size'] <= 250*1024*1024:
            raise ValueError('Missing or inconsistent checksum: ' + name)
        feed[kind] = {'url': url(asset), 'size': asset['size'], 'sha256': digest}
        if kind == 'web':
            html = fetch(url(asset), 150*1024*1024)
            if len(html) != asset['size'] or hashlib.sha256(html).hexdigest() != digest:
                raise ValueError('HTML integrity check failed')
            if b'<html' not in html[:4096].lower() or b'<script' not in html.lower():
                raise ValueError('Expected the standalone playable HTML')
    output.mkdir(parents=True, exist_ok=True)
    (output/'index.html').write_bytes(html)
    (output/'release.json').write_text(json.dumps(feed, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'.nojekyll').touch()
    print('Verified online play and Android feed: ' + version)
    return feed

if __name__ == '__main__':
    release = json.loads(get(f'https://api.github.com/repos/{REPOSITORY}/releases/latest', 1024*1024, token=True))
    prepare(release, get, Path('_site'))
