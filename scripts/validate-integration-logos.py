"""Validate local, passive assets without fetching or executing vendor content."""
import hashlib
import json
import pathlib
import re
import struct
import xml.etree.ElementTree as ET
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / 'public/images/integrations/manifest.json').read_text())
for key, asset in manifest['assets'].items():
    assert asset.get('license'), f'{key}: missing license/trademark note'
    if asset['kind'] != 'brand':
        assert asset['kind'] == 'initials' and asset.get('reason') and asset.get('text'), key
        continue
    assert asset['source'].startswith('https://') and asset['project'].startswith('https://'), key
    if any(license_id in asset['license'] for license_id in ['MIT', 'Apache-2.0', 'MPL-2.0', 'CC0', 'CC-BY-4.0']):
        assert asset.get('licenseFile') and (ROOT / 'public' / asset['licenseFile'].lstrip('/')).is_file(), f'{key}: missing upstream license text'
    for notice in asset.get('noticeFiles', []):
        assert (ROOT / 'public' / notice.lstrip('/')).is_file(), f'{key}: missing upstream notice'
    assert re.fullmatch(r'/images/integrations/[a-z0-9-]+\.(svg|png)', asset['file']), key
    file = ROOT / 'public' / asset['file'].lstrip('/')
    data = file.read_bytes()
    assert hashlib.sha256(data).hexdigest() == asset['sha256'], f'{key}: stale manifest hash'
    if file.suffix == '.svg':
        text = data.decode('utf-8')
        assert not re.search(r'<!DOCTYPE|<!ENTITY|<\?xml-stylesheet', text, re.I), key
        svg = ET.fromstring(text)
        assert svg.tag == '{http://www.w3.org/2000/svg}svg', key
        assert svg.get('viewBox') and svg.get('width') == '40' and svg.get('height') == '40', key
        for node in svg.iter():
            tag = node.tag.split('}')[-1].lower()
            assert tag not in {'script','foreignobject','iframe','object','embed','animate','set','animatetransform','animatemotion'}, key
            for attr, value in node.attrib.items():
                attr = attr.split('}')[-1].lower()
                assert not attr.startswith('on'), key
                if attr in {'href','src'}:
                    assert value.startswith('#'), key
                assert not re.search(r'url\(\s*["\']?(?!#)[^)]',value,re.I), key
            if tag == 'style':
                assert not re.search(r'@import|url\(\s*["\']?(?!#)',node.text or '',re.I), key
    else:
        assert data[:8] == b'\x89PNG\r\n\x1a\n', key
        width, height = struct.unpack('>II', data[16:24])
        assert 0 < width <= 128 and 0 < height <= 128, key
        offset = 8
        while offset < len(data):
            length = struct.unpack('>I',data[offset:offset+4])[0]
            chunk = data[offset+4:offset+8+length]
            crc = struct.unpack('>I',data[offset+8+length:offset+12+length])[0]
            assert zlib.crc32(chunk) == crc, f'{key}: invalid PNG chunk'
            offset += length + 12
        assert offset == len(data), key
print(f"Validated {len(manifest['assets'])} logo/provenance records")
