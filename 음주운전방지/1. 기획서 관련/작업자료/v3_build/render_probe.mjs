import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const root='C:/Users/windows10/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool';
process.on('exit',c=>console.log('EXIT',c));
process.on('uncaughtException',e=>console.error('UNCAUGHT',e));
try {
 console.log('IMPORT SKIA');
 const m=await import(pathToFileURL(root+'/node_modules/skia-canvas/lib/index.js').href);
 console.log('SKIA',Object.keys(m));
 console.log('REGISTER',m.FontLibrary.use('Malgun Gothic',['C:/Windows/Fonts/malgun.ttf','C:/Windows/Fonts/malgunbd.ttf']));
 const canvas=new m.Canvas(200,100,{gpu:false});console.log('CREATED');let ctx=canvas.getContext('2d');console.log('CONTEXT');ctx.fillStyle='white';ctx.fillRect(0,0,200,100);console.log('RECT');ctx.font='24px "Malgun Gothic"';console.log('FONT');ctx.fillStyle='black';ctx.fillText('한글 테스트',10,40);console.log('DRAWN');
 await fs.writeFile(new URL('probe.png',import.meta.url),await canvas.toBuffer('png'));console.log('SAVED');
} catch(e){console.error('ERROR',e,e.stack)}

