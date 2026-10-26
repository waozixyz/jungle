"""Validate the real website metadata and every platform's exported brand assets."""
from html.parser import HTMLParser
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class Head(HTMLParser):
    def __init__(self):
        super().__init__(); self.links={}; self.meta={}; self.jsonld=''; self.in_json=False
    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if tag=='link': self.links[values.get('rel')]=values.get('href')
        if tag=='meta': self.meta[values.get('property',values.get('name'))]=values.get('content')
        if tag=='script' and values.get('type')=='application/ld+json': self.in_json=True
    def handle_endtag(self, tag):
        if tag=='script': self.in_json=False
    def handle_data(self,data):
        if self.in_json:self.jsonld+=data


head=Head();head.feed((ROOT/'web/index.html').read_text())
assert head.links['canonical']=='https://jungle.waozi.xyz/'
for key in ('description','og:title','og:description','og:image','og:image:alt','twitter:title','twitter:image'):
    assert head.meta[key],key
schema=json.loads(head.jsonld)
assert schema['@type']=='SoftwareApplication' and schema['inLanguage']==['en','de','es']
assert schema['offers']['price']=='0' and schema['url']==head.links['canonical']
manifest=json.loads((ROOT/'web/site.webmanifest').read_text())
assert manifest['start_url']==manifest['scope']==manifest['id']=='/'
assert {icon['purpose'] for icon in manifest['icons']}=={'any','maskable'}
for icon in manifest['icons']:
    with Image.open(ROOT/icon['src'].lstrip('/')) as image:
        assert f'{image.width}x{image.height}'==icon['sizes']
for size in (16,32,48,64,128,180,192,256,512,1024):
    with Image.open(ROOT/f'assets/jungle/icons/icon-{size}.png') as image:
        assert image.size==(size,size)
with Image.open(ROOT/'assets/jungle/branding/logo.png') as image:
    assert image.mode=='RGBA' and image.width>image.height*2
    assert image.getchannel('A').getextrema()==(0,255)
with Image.open(ROOT/'assets/jungle/icons/favicon.ico') as image:
    assert (32,32) in image.ico.sizes() and (256,256) in image.ico.sizes()
for density,size in (('mdpi',48),('hdpi',72),('xhdpi',96),('xxhdpi',144),('xxxhdpi',192)):
    with Image.open(ROOT/f'droid/app/src/main/res/mipmap-{density}/ic_launcher.png') as image:assert image.size==(size,size)
ET.parse(ROOT/'droid/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml')
ET.parse(ROOT/'packaging/xyz.waozi.jungle.metainfo.xml')
print('local brand metadata test: canonical/share metadata, structured data, web manifest, logo and desktop/Android icon sizes passed')
