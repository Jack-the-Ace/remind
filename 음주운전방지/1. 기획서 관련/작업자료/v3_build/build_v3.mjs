import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const BUILD=path.dirname(fileURLToPath(import.meta.url));
const BASE=path.resolve(BUILD,'../..');
const OUT=path.join(BASE,'산출물');
const PRE=path.join(BASE,'슬라이드 미리보기_v3');
const RT='C:/Users/windows10/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const SKILL='C:/Users/windows10/.codex/plugins/cache/openai-primary-runtime/presentations/26.1110.11613/skills/presentations';
process.env.RUNTIME_NODE_MODULES=RT+'/node/node_modules';
const {Presentation,PresentationFile,FileBlob}=await import(pathToFileURL(RT+'/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs').href);
const source=JSON.parse(await fs.readFile(path.join(BUILD,'source_content.json'),'utf8'));
await fs.mkdir(PRE,{recursive:true});
const C={navy:'#142B43',text:'#293B4A',muted:'#526A7B',teal:'#087F83',pale:'#EAF5F4',light:'#F2F5F7',line:'#CBD9E1',green:'#16865D',orange:'#B66A08',red:'#BE3C46',white:'#FFFFFF'};
const FONT='Malgun Gothic';
const P=Presentation.create({slideSize:{width:1280,height:720}});
let seq=0,phs=[]; const copies=[];
function shape(s,x,y,w,h,fill='none',stroke='none',sw=0,geometry='rect',name){return s.shapes.add({geometry,name:name||'object-'+(++seq),position:{left:x,top:y,width:w,height:h},fill,line:{fill:stroke,width:sw,style:'solid'}})}
function txt(s,t,x,y,w,h,size=26,color=C.text,bold=false,align='left',name){let q=shape(s,x,y,w,h,'none','none',0,'textbox',name);q.text=t;q.text.style={typeface:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:'top',autoFit:'none',wrap:'square',insets:0};copies.push({slide:P.slides.items.indexOf(s)+1,text:t});return q;}
function rule(s,x,y,w,color=C.line,h=1){return shape(s,x,y,w,h,color)}
function arrow(s,x,y,w=38,h=24,color=C.teal){return shape(s,x,y,w,h,color,'none',0,'rightArrow')}
function down(s,x,y,w=24,h=28){return shape(s,x,y,w,h,C.teal,'none',0,'downArrow')}
function base(n,title,section,sub='') {let s=P.slides.add();s.background.fill=C.white;txt(s,section,56,28,900,25,17,C.teal,true);txt(s,title,56,72,1168,60,40,C.navy,true);if(sub)txt(s,sub,58,132,1160,38,24,C.muted);rule(s,56,681,1168);txt(s,'ROAD WATCH   ·   구현 전 기획',56,692,900,20,15,C.muted);txt(s,String(n).padStart(2,'0'),1168,688,56,26,18,C.navy,true,'right');return s;}
function notes(s,n,extra='') {const orig=source.slides[n-1];const detail=orig.text.filter(t=>t&&!t.startsWith('ROAD WATCH  /')&&!/^\d{2}$/.test(t));s.speakerNotes.text=[extra,...orig.notes.filter(Boolean),'상세 설명',...detail].filter(Boolean).join('\n\n');}
function placeholder(s,n,x,y,w,h,label,options={}){let q=shape(s,x,y,w,h,C.light,C.line,2,'rect','PHOTO_'+String(n).padStart(2,'0'));if(!options.noTag)txt(s,'사진 삽입 영역 '+String(n).padStart(2,'0'),x+24,y+20,w-48,30,18,C.teal,true);txt(s,label,x+30,y+(options.labelY??h/2-35),w-60,options.labelH??115,26,C.muted,false,'center','PHOTO_LABEL_'+n);phs.push({number:n,slide:P.slides.items.indexOf(s)+1,x,y,w,h,label});return q;}
function lineItem(s,num,title,body,x,y,w=350){txt(s,num,x,y,55,44,32,C.teal,true);txt(s,title,x+68,y,w-68,42,30,C.navy,true);if(body)txt(s,body,x+68,y+51,w-68,70,25,C.muted);}
// 01
{
 const s=P.slides.add();s.background.fill=C.white;
 txt(s,'컴퓨터 비전 AI 서비스 기획',56,38,440,30,20,C.teal,true);
 txt(s,'ROAD\nWATCH',56,128,430,166,68,C.navy,true);
 txt(s,'의심 차량을 추적하고\n검토할 장면을 남깁니다',58,329,438,104,34,C.navy,true);
 txt(s,'AI 위험주행 감지\n증거 기록·신고 지원',58,470,420,84,28,C.muted);
 placeholder(s,1,520,113,704,528,'[전방 블랙박스에서 차량을 추적하는\n화면 이미지 첨부 필요]');
 rule(s,56,670,1168);txt(s,'11.16 기획서 제출     11.30 작동 MVP     12.22 2PC 시연',56,687,1168,27,22,C.teal,true);
 notes(s,1,'ROAD WATCH는 사람이 먼저 지정한 차량을 AI로 추적하고 위험 의심 장면을 기록해 신고 검토를 지원하는 서비스 기획이다. 사진과 추적 화면은 실제 시연 자료를 삽입한다.');
}
// 02
{
 const s=base(2,'위험을 발견해도, 기록은 어렵습니다','문제 정의');
 placeholder(s,2,56,155,718,500,'[도로에서 비정상적으로 이동하는 차량의\n블랙박스 사진 첨부 필요]');
 lineItem(s,'01','대상 차량을 놓침','겹친 차량 사이에서\n같은 차량을 찾기 어려움',814,176,410);
 lineItem(s,'02','긴 영상을 재탐색','의심 시각과 장면을\n다시 찾아야 함',814,326,410);
 lineItem(s,'03','시간 맥락이 부족','한 장면만으로 반복 행동을\n설명하기 어려움',814,476,410);
 notes(s,2);
}
// 03
{
 const s=base(3,'차량과 시간을 연결하는 AI 검토 도구','사용자와 핵심 가치','1차 사용자: 블랙박스 영상 보유 시민   /   확장: 운행사업자 안전 담당자');
 txt(s,'사용자 불편',56,213,500,42,30,C.navy,true);txt(s,'ROAD WATCH의 해결 방식',688,213,536,42,30,C.teal,true);
 const rows=[['같은 차량을 다시 찾음','선택 차량의 ID를 지속 추적'],['긴 영상을 반복 재생','의심 이벤트의 시각·횟수 표시'],['장면을 수작업으로 정리','클립·근거를 저장해 사람이 검토']];
 rows.forEach((r,i)=>{let y=291+i*80;txt(s,r[0],56,y,490,42,28);arrow(s,585,y+6,48,26);txt(s,r[1],688,y,536,42,28,C.navy,i===2);rule(s,56,y+59,1168)});
 txt(s,'선택한 차량의 의심 장면을, 검토 가능한 기록으로',56,567,1168,48,34,C.teal,true);
 txt(s,'검증 계획: 사용자 5명 비교 평가 · 정리 시간 30% 절감 목표 · 효과 미검증',58,631,1164,32,22,C.muted);
 notes(s,3);
}
// 04
{
 const s=base(4,'사람이 지정하고, AI가 분석하고, 사람이 검토합니다','서비스 비전');
 const steps=[['발견','위험 의심 상황 관찰'],['차량 선택','사람이 한 대 지정'],['AI 추적·분석','동일 ID와 차선 관계'],['기록·검토','증거 확인 후 보관']];
 steps.forEach((a,i)=>{const x=56+i*300;txt(s,String(i+1).padStart(2,'0'),x,214,250,64,49,C.teal,true);rule(s,x,296,268,i===2?C.teal:C.line,4);txt(s,a[0],x,330,268,45,32,C.navy,true);txt(s,a[1],x,393,268,68,25,C.muted);if(i<3)arrow(s,x+263,244,30,25)});
 rule(s,56,511,1168);txt(s,'11월',56,548,170,43,34,C.teal,true);txt(s,'추적·차선 학습·이벤트 기록',238,550,986,42,30,C.navy,true);
 txt(s,'12월',56,612,170,43,34,C.teal,true);txt(s,'2PC 모의 관제와 후보 차량 연결',238,614,986,42,30,C.navy,true);
 notes(s,4);
}
// 05
{
 const s=base(5,'입력부터 저장까지, 세 화면으로 연결합니다','UX/UI 와이어프레임','PC에서 허가된 영상을 사후 분석하는 11월 MVP');
 const xs=[56,465,874],w=350;
 ['01  영상 입력','02  분석 대기','03  결과 검토'].forEach((t,i)=>{const x=xs[i];txt(s,t,x,206,w,43,30,C.navy,true);shape(s,x,267,w,290,C.white,C.line,2);rule(s,x,267,w,C.navy,40);txt(s,'ROAD WATCH',x+18,275,w-36,26,18,C.white,true);if(i<2)arrow(s,x+w+12,389,32,28)});
 shape(s,80,333,302,90,C.light,C.line,1);txt(s,'영상 파일 선택',96,357,270,41,29,C.teal,true,'center');txt(s,'정지 화면에서 차량 선택',80,460,302,67,25,C.muted,false,'center');
 txt(s,'선택 ID 27 분석 중',489,337,302,40,27,C.navy,true);shape(s,489,405,302,12,C.light);shape(s,489,405,195,12,C.teal);txt(s,'검출 · 추적 · 차선 분석',489,446,302,64,24,C.muted);txt(s,'취소',489,511,302,32,24,C.teal,true);
 txt(s,'00:18  차선 이탈 의심',898,336,302,39,24,C.orange,true);rule(s,898,390,302);txt(s,'근거 확인 · 오탐 제외',898,421,302,36,24,C.muted);txt(s,'클립·기록 저장',898,495,302,40,28,C.teal,true);
 txt(s,'추적 상실·차선 불명확',56,605,420,40,29,C.navy,true);arrow(s,500,611,48,25);txt(s,'판단 보류 후, 사용자 확인·재선택',590,605,634,43,29,C.teal,true);
 notes(s,5);
}
// 06
{
 const s=base(6,'선택 차량과 위험 의심 이벤트를 한 화면에','메인 서비스 UI','구현 예정 와이어프레임 · 아래 상태와 이벤트 수는 가상 예시');
 placeholder(s,3,56,183,888,473,'[특정 차량을 바운딩 박스로 추적하고\n위험 의심 이벤트를 표시한 화면 첨부 필요]',{labelY:89,labelH:85,noTag:true});
 shape(s,56,183,888,50,C.navy);txt(s,'위험 의심 2건    /    검토 대기 1건',76,193,844,38,27,C.white,true);
 shape(s,158,413,128,98,'none',C.green,4);txt(s,'ID 08',158,523,140,36,24,C.green,true);
 shape(s,400,387,160,126,'none',C.orange,4);txt(s,'ID 27 · 검토',400,524,235,36,24,C.orange,true);
 shape(s,704,422,118,92,'none',C.red,4);txt(s,'신고 검토',694,526,200,36,24,C.red,true);
 rule(s,76,581,846);txt(s,'00:18   + 차선 이탈 의심 1',76,608,844,37,26,C.orange,true);
 [['초록','추적 중',C.green],['주황','추가 검토',C.orange],['빨강','신고 검토',C.red]].forEach((a,i)=>{let y=212+i*116;shape(s,978,y+6,12,29,a[2]);txt(s,a[0],1007,y,217,36,27,a[2],true);txt(s,a[1],1007,y+48,217,39,27,C.navy,true)});
 txt(s,'회색  판단 보류',978,572,246,37,25,C.muted,true);txt(s,'법적 위반 확정 아님',978,623,246,32,22,C.muted);
 notes(s,6,'화면 예시의 초록·주황·빨강 테두리와 이벤트 카운터는 수정 가능한 PowerPoint 도형이다. 초록은 추적 상태이며 안전운전 확정을 뜻하지 않는다.');
}
// 07
{
 const s=base(7,'차량 검출부터 이벤트 분석까지','AI 기술 전략');
 const data=[['YOLO Nano','차량 검출'],['ByteTrack','선택 ID 지속 Tracking'],['차선 Segmentation','DeepLabV3-MobileNetV3'],['이벤트 분석','OpenCV + 시간 규칙']];
 data.forEach((a,i)=>{const y=159+i*120;txt(s,String(i+1).padStart(2,'0'),56,y,54,38,26,C.teal,true);txt(s,a[0],126,y,356,40,i===2?28:31,C.navy,true);txt(s,a[1],126,y+47,356,48,i===2?23:25,C.muted);if(i<3)down(s,71,y+65,22,35)});
 placeholder(s,4,525,155,699,480,'[YOLO가 여러 자동차를 검출하고\n선택 ID를 추적하는 화면 첨부 필요]');
 txt(s,'수업 코드 재활용 · 차선 모델은 실제 파인튜닝',56,645,1168,30,23,C.teal,true);
 notes(s,7,'구현 계획: 사전학습 차량 검출 모델과 ByteTrack을 재활용하고 차선 인식은 직접 학습한다. 차선이 흐리거나 자차 회전으로 관계가 불확실하면 판단을 보류한다.');
}
// 08
{
 const s=base(8,'차선 데이터를 라벨링하고, 실제로 학습합니다','데이터·딥러닝 학습');
 placeholder(s,5,56,157,568,325,'[흰색·노란색 실선·점선의\n차선 라벨링 화면 첨부 필요]',{labelY:112,labelH:110});
 placeholder(s,6,656,157,568,325,'[차선 학습 결과·성능 곡선 또는\nRoboflow 과정 캡처 첨부 필요]',{labelY:112,labelH:110});
 txt(s,'확보',56,515,134,38,29,C.teal,true);txt(s,'분할',356,515,134,38,29,C.teal,true);txt(s,'학습',656,515,134,38,29,C.teal,true);txt(s,'비교·평가',956,515,268,38,29,C.teal,true);
 [[56,'600~1,200장 목표\n미확보 시 300장'],[356,'영상 단위\n70 / 15 / 15'],[656,'20~40 epoch\n2클래스 차선'],[956,'OpenCV 기준선\n학습 전·후 비교']].forEach(([x,t])=>txt(s,t,x,562,268,76,25,C.navy));
 txt(s,'후보: AI Hub 197·196 / BDD100K / KITTI Tracking / CULane · 승인·조건 확인 후 사용',56,650,1168,28,20,C.muted);
 notes(s,8,'이미지 삽입 시 허가된 자료만 사용한다. CVAT 로컬을 기본으로 검토하며 Roboflow는 본인 권리 자료와 서비스 이용 조건을 확인한 경우에만 사용한다. 차선 색·실선/점선 속성을 보존하되 11월 필수 학습은 차선/배경 이진 segmentation이다.');
}
// 09
{
 const s=base(9,'React 화면과 Python 영상 분석의 연결','시스템 아키텍처','11월 실행 범위: 한 PC의 로컬 웹');
 const nodes=[['React + Vite','입력·차량 선택'],['FastAPI','분석 작업 관리'],['YOLO / OpenCV','PyTorch 영상 분석'],['이벤트 저장','클립·JSON/CSV']];
 nodes.forEach((a,i)=>{let x=56+i*300;shape(s,x,235,268,188,i===2?C.pale:C.light,C.line,1);txt(s,a[0],x+18,264,232,47,i===2?26:29,C.navy,true);txt(s,a[1],x+18,343,232,60,25,C.muted);if(i<3)arrow(s,x+273,311,24,28)});
 rule(s,56,486,1168);txt(s,'저장 정보',56,524,270,44,31,C.teal,true);txt(s,'영상 시각 · 선택 ID · 이벤트 근거 · 보류 사유',356,524,868,47,29,C.navy,true);txt(s,'원본 참조와 분석 기록을 구분해 SQLite에 보관',356,595,868,43,26,C.muted);
 notes(s,9);
}
// 10
{
 const s=base(10,'11월 30일, AI 콘텐츠가 실제로 작동해야 합니다','11월 MVP');
 txt(s,'필수 완성 기능',56,192,690,45,32,C.navy,true);
 const rows=['차량 선택과 지속 추적','차선 모델의 실제 학습·추론','자동 이벤트 1종 + 3색·횟수','클립·근거 기록 저장'];
 rows.forEach((t,i)=>{let y=269+i*83;shape(s,58,y+3,25,25,'none',C.teal,2);txt(s,t,104,y-3,678,48,31,C.navy,true);rule(s,56,y+55,706)});
 txt(s,'제출 근거',848,194,376,43,31,C.teal,true);txt(s,'작동 시연 영상\n학습 가중치·곡선\n독립 test와 실패 사례',848,266,376,163,28,C.navy);rule(s,848,466,376);txt(s,'추적 유지율 ≥90%\nlane IoU ≥0.50',848,497,376,87,28,C.teal,true);txt(s,'검증 전 초기 목표',848,607,376,35,24,C.muted);
 notes(s,10,'체크리스트는 구현 예정 필수 범위이며 완료 상태를 표시하지 않는다. 실제 학습과 자동 이벤트를 유지하고 OCR·모바일 등 확장 항목은 범위를 줄일 때 제외한다.');
}
// 11
{
 const s=base(11,'기획 제출부터 작동 MVP까지의 일정','개발 로드맵','2026년 11월 · 주 개발 1명 / 팀원 1명 검토·시연 지원');
 const xs=[56,294,532,770,1008];const stages=[['11.12~16','기획·환경','11.16 제출'],['11.17~20','선택·추적','라벨 확보'],['11.21~24','차선 학습','가중치·곡선'],['11.25~27','이벤트·저장','3색·카운트'],['11.28~30','평가·시연','11.30 완성']];
 rule(s,56,306,1168,C.line,5);
 stages.forEach((a,i)=>{let x=xs[i];shape(s,x,296,24,24,i===4?C.navy:C.teal,'none',0,'ellipse');txt(s,a[0],x,234,216,37,27,C.teal,true);txt(s,a[1],x,350,216,45,29,C.navy,true);txt(s,a[2],x,413,216,66,25,C.muted)});
 rule(s,56,516,1168);txt(s,'11.18',56,551,160,44,31,C.teal,true);txt(s,'데이터 미확보 시, 허가 영상 300장 대안으로 전환',242,550,982,47,28,C.navy,true);txt(s,'11.30',56,615,160,44,31,C.teal,true);txt(s,'실제 학습·차량 추적·차선 분석의 작동 확인',242,614,982,47,28,C.navy,true);
 notes(s,11);
}
// 12
{
 const s=base(12,'12월 22일, 두 컴퓨터로 모의 관제 시연','12월 최종과제');
 txt(s,'컴퓨터 1',56,164,440,48,35,C.navy,true);txt(s,'차량 감지·추적·분석',56,226,440,41,28,C.text);
 txt(s,'LAN / API',530,165,190,35,24,C.teal,true,'center');arrow(s,530,225,190,32);txt(s,'이벤트·시각·클립',496,283,258,35,23,C.muted,false,'center');
 txt(s,'컴퓨터 2',800,164,424,48,35,C.navy,true);txt(s,'모의 CCTV 후보 확인·연결',800,226,424,75,28,C.text);
 placeholder(s,7,56,339,1168,269,'[두 컴퓨터가 연결된 분석·모의 관제 시스템 시연 사진 첨부 필요]',{labelY:112,labelH:90});
 txt(s,'허가 영상·로컬 네트워크 사용 · 실제 경찰/CCTV 접속 없음 · 후보 연결은 사람이 확인',56,637,1168,33,23,C.teal,true);
 notes(s,12);
}
// 13
{
 const s=base(13,'불확실할 때 멈추고, 사람이 검토합니다','기술적 한계·안전·개인정보');
 const rows=[['01','차선 소실·가림·자차 회전','판단 보류 / HOLD·LOST'],['02','운전 중 조작·위험 차량 추격','PC 사후 검토 / 추격 유도 금지'],['03','번호판·위치·영상 노출','로컬 접근 제한 / 공유용 마스킹'],['04','잘못된 신고·기록 방치','사람의 근거 확인 / 보관·삭제 정책']];
 rows.forEach((a,i)=>{let y=189+i*109;txt(s,a[0],56,y+3,80,45,31,C.teal,true);txt(s,a[1],162,y,495,47,29,C.navy,true);arrow(s,689,y+8,38,25);txt(s,a[2],779,y,445,74,27,C.text);rule(s,56,y+83,1168)});
 txt(s,'법적 위반·음주 여부를 확정하지 않음 · 112 연결은 모의 UI로 시연',56,647,1168,31,23,C.muted);
 notes(s,13,'운전 중에는 조작과 추격을 유도하지 않는다. 차선 경계나 추적 대상이 불명확하면 자동 집계를 멈추고 판단 보류 사유를 표시한다. 개인정보 관련 내용은 현재의 보호 설계 방향이며 실제 운영 전에 법적 근거·촬영 고지·보관 범위를 검토해야 한다.');
}
// 14
{
 const s=base(14,'모바일 기록과 신고 지원으로 확장','사업화 비전');
 const stages=[['01','모바일·음성 신고','최대 10분 분석 구상'],['02','차선과 무관한 신고','불법주차 등 독립 탐지'],['03','기관·서비스 협력','내비 연동·경찰청 협력 검토']];
 stages.forEach((a,i)=>{let y=165+i*145;txt(s,a[0],56,y,60,43,29,C.teal,true);txt(s,a[1],129,y,355,46,29,C.navy,true);txt(s,a[2],129,y+57,355,70,24,C.muted);if(i<2)down(s,72,y+75,22,35)});
 placeholder(s,8,520,155,704,465,'[모바일 앱 사용 장면 또는\n미래 서비스 화면 목업 첨부 필요]');
 txt(s,'사업 가설: 개인 기록 구독\n운행사업자 검토 도구',56,604,435,69,24,C.teal,true);txt(s,'경찰청 협력은 미래 비전이며,\n현재 확정된 협약이 아닙니다',520,631,704,47,20,C.muted);
 notes(s,14,'장기 확장 로드맵이며 현재 구현 완료 기능이 아니다. 앱·음성 신고·불법주차 탐지·경찰청 협력은 기술 검증과 권한·정책 확인 후 검토한다. 수익모델 역시 가설이다.');
}
await fs.writeFile(path.join(BUILD,'copy_v3.json'),JSON.stringify({copies,placeholders:phs},null,2));
await fs.writeFile(path.join(BUILD,'presentation_v3.json'),JSON.stringify(P.toProto()));
const candidate=path.join(BUILD,'v3_candidate.pptx');
await(await PresentationFile.exportPptx(P)).save(candidate);
console.log('CANDIDATE',candidate,'SLIDES',P.slides.items.length,'PLACEHOLDERS',phs.length);
if(process.env.NATIVE_RENDER==='1')for(let i=0;i<P.slides.items.length;i++){let s=P.slides.items[i];let stem='slide-'+String(i+1).padStart(2,'0');let png=await P.export({slide:s,format:'png',scale:1.5});await fs.writeFile(path.join(PRE,stem+'.png'),new Uint8Array(await png.arrayBuffer()));console.log('RENDERED',i+1)}
console.log('DONE');
