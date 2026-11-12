import zipfile, xml.etree.ElementTree as E, json, pathlib, hashlib
root=pathlib.Path(__file__).resolve().parents[2]
src=root/'산출물/AI_위험주행_차량추적_11월_기획서_초안_v2.pptx'
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
def paragraphs(data):
    return [''.join(t.text or '' for t in p.findall('.//a:t',ns)) for p in E.fromstring(data).findall('.//a:p',ns)]
with zipfile.ZipFile(src) as z:
    slides=[{'slide':i,'text':paragraphs(z.read(f'ppt/slides/slide{i}.xml')),'notes':paragraphs(z.read(f'ppt/notesSlides/notesSlide{i}.xml'))} for i in range(1,15)]
    size=E.fromstring(z.read('ppt/presentation.xml')).find('p:sldSz',ns).attrib
out={'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'size':size,'slides':slides}
(pathlib.Path(__file__).parent/'source_content.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'slides':len(slides),'characters':sum(len(''.join(s['text'])) for s in slides),'size':size,'sha256':out['source_sha256']},ensure_ascii=True))
