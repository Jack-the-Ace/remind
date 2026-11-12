import zipfile,xml.etree.ElementTree as E,pathlib,json,sys
B=pathlib.Path(__file__).resolve().parent
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
def fill(node):
    if node is None:return 'none'
    c=node.find('a:solidFill/a:srgbClr',ns)
    return '#'+c.get('val') if c is not None else 'none'
def val(node,key,default):return node.get(key,default) if node is not None else default
z=zipfile.ZipFile(sys.argv[1] if len(sys.argv)>1 else B/'v3_candidate.pptx')
slides=[]
for i in range(1,15):
    r=E.fromstring(z.read(f'ppt/slides/slide{i}.xml')); shapes=[]
    for s in r.findall('.//p:spTree/p:sp',ns):
        pr=s.find('p:spPr',ns); off=pr.find('a:xfrm/a:off',ns); ext=pr.find('a:xfrm/a:ext',ns)
        if off is None or ext is None:continue
        geo=pr.find('a:prstGeom',ns); ln=pr.find('a:ln',ns)
        d={'name':s.find('p:nvSpPr/p:cNvPr',ns).get('name'),'x':int(off.get('x'))/9525,'y':int(off.get('y'))/9525,'w':int(ext.get('cx'))/9525,'h':int(ext.get('cy'))/9525,'fill':fill(pr),'stroke':fill(ln),'sw':int(val(ln,'w','0'))/9525,'geom':val(geo,'prst','rect'),'paragraphs':[]}
        for p in s.findall('p:txBody/a:p',ns):
            runs=[]; pp=p.find('a:pPr',ns)
            for run in p.findall('a:r',ns):
                rp=run.find('a:rPr',ns); t=run.find('a:t',ns);font=rp.find('a:latin',ns) if rp is not None else None
                runs.append({'text':t.text or '' if t is not None else '', 'size':int(val(rp,'sz','1800'))/75,'bold':val(rp,'b','0')=='1','color':fill(rp),'font':val(font,'typeface','Malgun Gothic')})
            if runs:d['paragraphs'].append({'align':val(pp,'algn','l'),'runs':runs})
        shapes.append(d)
    slides.append(shapes)
(B/'render_shapes.json').write_text(json.dumps(slides,ensure_ascii=False),encoding='utf8')
print('Extracted 14 slides for local browser rendering')
