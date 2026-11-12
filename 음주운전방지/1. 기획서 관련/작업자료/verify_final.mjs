import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const rt='C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1111-570-0_26.1111.570.0_x64__3k8sg7r9htsxt/dependencies';
const {FileBlob,PresentationFile}=await import(pathToFileURL(rt+'/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs').href);
const b=path.resolve('1. 기획서 관련');
const final=path.join(b,'산출물','AI_위험주행_차량추적_11월_기획서_초안_v2.pptx');
const p=await PresentationFile.importPptx(await FileBlob.load(final));
const d=path.join(b,'슬라이드 미리보기');
for(let i=0;i<p.slides.items.length;i++){
 const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(d,'slide-'+String(i+1).padStart(2,'0')+'.png'),new Uint8Array(await blob.arrayBuffer()));
}
console.log('Reimported final PPTX and rendered',p.slides.items.length,'slides');
