"""公開フィードの接続確認（手動実行専用）。"""
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trendwatch import http
from trendwatch.config import load_config
URLS = [spec['feed'] for spec in load_config().raw.get('media', {}).get('publishers', {}).values()]
for url in sys.argv[1:] or URLS:
    r = http.get(url, timeout=20, retries=1)
    if r is None:
        print(url, 'FAILED', flush=True)
        continue
    try:
        root = ET.fromstring(r.content)
        items = root.findall('.//item') or root.findall('{http://www.w3.org/2005/Atom}entry')
        print(url, r.status_code, root.tag, 'items',len(items), 'sample',ET.tostring(items[0],encoding='unicode')[:550] if items else '', flush=True)
    except ET.ParseError:
        print(url, r.status_code, 'NOT_XML',r.text[:120],flush=True)
