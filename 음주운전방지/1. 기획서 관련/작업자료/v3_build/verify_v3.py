import pathlib,zipfile,xml.etree.ElementTree as E,json,hashlib
B=pathlib.Path(__file__).resolve().parent
source=json.loads((B/'source_content.json').read_text(encoding='utf8'))
root=B.parents[1]
v2=root/'산출물/AI_위험주행_차량추적_11월_기획서_초안_v2.pptx'
v3=root/'산출물/AI_위험주행_차량추적_11월_기획서_초안_v3.pptx'
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
missing=[];count=0;ph=0;original_count=sum(len(''.join(s['text'])) for s in source['slides'])
with zipfile.ZipFile(v3) as z:
    for i in range(1,15):
        r=E.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
        count+=sum(len(t.text or '') for t in r.findall('.//a:t',ns))
        ph+=sum(s.get('name','').startswith('PHOTO_') and not s.get('name','').startswith('PHOTO_LABEL_') for s in r.findall('.//p:cNvPr',ns))
        n='\n'.join(t.text or '' for t in E.fromstring(z.read(f'ppt/notesSlides/notesSlide{i}.xml')).findall('.//a:t',ns))
        for p in source['slides'][i-1]['notes']:
            if p and p not in n:missing.append({'slide':i,'kind':'original_note'})
        for p in source['slides'][i-1]['text']:
            if p and not p.startswith('ROAD WATCH  /') and not (p.isdigit() and len(p)==2) and p not in n:missing.append({'slide':i,'kind':'original_detail'})
    slides=len([n for n in z.namelist() if __import__('re').fullmatch(r'ppt/slides/slide\d+\.xml',n)])
    size=E.fromstring(z.read('ppt/presentation.xml')).find('p:sldSz',ns).attrib
unchanged=hashlib.sha256(v2.read_bytes()).hexdigest()==source['source_sha256']
result={'source_unchanged':unchanged,'slides':slides,'size':size,'photo_regions':ph,'original_characters':original_count,'v3_characters':count,'visible_text_reduction_percent':round((1-count/original_count)*100,1),'missing_original_notes_or_details':missing,'v3_sha256':hashlib.sha256(v3.read_bytes()).hexdigest()}
(B/'v3_content_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=True,indent=2))
assert unchanged and slides==14 and ph==8 and not missing
