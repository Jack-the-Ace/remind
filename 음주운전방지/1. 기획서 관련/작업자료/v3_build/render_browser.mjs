import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const B=path.dirname(fileURLToPath(import.meta.url));
const {chromium}=await import(pathToFileURL('C:/Users/windows10/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs').href);
const shapes=JSON.parse(await fs.readFile(path.join(B,'render_shapes.json'),'utf8'));
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const OUT=path.resolve(B,'../../슬라이드 미리보기_v3');await fs.mkdir(OUT,{recursive:true});
function draw(s){const {x,y,w,h,fill,stroke,sw}=s;let g='';const common=`fill="${fill}" stroke="${stroke}" stroke-width="${sw}"`;
 if(s.geom==='rightArrow'){g=`<polygon points="${x},${y+h*.25} ${x+w*.66},${y+h*.25} ${x+w*.66},${y} ${x+w},${y+h/2} ${x+w*.66},${y+h} ${x+w*.66},${y+h*.75} ${x},${y+h*.75}" ${common}/>`}
 else if(s.geom==='downArrow'){g=`<polygon points="${x+w*.25},${y} ${x+w*.75},${y} ${x+w*.75},${y+h*.66} ${x+w},${y+h*.66} ${x+w/2},${y+h} ${x},${y+h*.66} ${x+w*.25},${y+h*.66}" ${common}/>`}
 else if(s.geom==='ellipse'){g=`<ellipse cx="${x+w/2}" cy="${y+h/2}" rx="${w/2}" ry="${h/2}" ${common}/>`}
 else g=`<rect x="${x}" y="${y}" width="${w}" height="${h}" ${common}/>`;
 if(s.paragraphs.length){g+=`<foreignObject x="${x}" y="${y}" width="${w}" height="${h+100}"><div xmlns="http://www.w3.org/1999/xhtml" data-name="${esc(s.name)}" data-height="${h}" style="width:${w}px;overflow:visible;word-break:keep-all;overflow-wrap:anywhere;line-height:1.16;">`+s.paragraphs.map(p=>`<div style="text-align:${({l:'left',ctr:'center',r:'right'})[p.align]||'left'};white-space:pre-wrap">`+p.runs.map(r=>`<span style="font-family:'${r.font}';font-size:${r.size}px;font-weight:${r.bold?700:400};color:${r.color}">${esc(r.text)}</span>`).join('')+'</div>').join('')+'</div></foreignObject>';}return g;
}
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-first-run','--disable-extensions','--disable-background-networking']});
const page=await browser.newPage({viewport:{width:1280,height:720},deviceScaleFactor:1.5});const issues=[];
for(let i=0;i<shapes.length;i++){let html=`<!doctype html><meta charset="utf-8"><style>html,body{margin:0;padding:0;background:white}*{box-sizing:border-box}</style><svg width="1280" height="720" xmlns="http://www.w3.org/2000/svg">${shapes[i].map(draw).join('')}</svg>`;await fs.writeFile(path.join(B,`slide-${i+1}.html`),html);await page.setContent(html);await page.evaluate(()=>document.fonts.ready);const overflow=await page.locator('[data-name]').evaluateAll(es=>es.map(e=>({name:e.dataset.name,actual:e.getBoundingClientRect().height,available:Number(e.dataset.height)})).filter(x=>x.actual>x.available+1));if(overflow.length)issues.push({slide:i+1,overflow});await page.screenshot({path:path.join(OUT,`slide-${String(i+1).padStart(2,'0')}.png`)});console.log('RENDERED',i+1)}
await fs.writeFile(path.join(B,'browser_render_checks.json'),JSON.stringify({renderer:'local Chromium preview from PPTX XML geometry and text; not native PowerPoint',issues},null,2));console.log('OVERFLOW',JSON.stringify(issues));await browser.close();
