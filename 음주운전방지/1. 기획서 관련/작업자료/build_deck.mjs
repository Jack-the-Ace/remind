import fs from 'node:fs/promises';
import {constants as fsConstants} from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const RT='C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1111-570-0_26.1111.570.0_x64__3k8sg7r9htsxt/dependencies';
process.env.RUNTIME_NODE_MODULES=RT+'/node/node_modules';
const {Presentation,PresentationFile}=await import(pathToFileURL(RT+'/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs').href);
const SKILL='C:/Users/mbc/.codex/plugins/cache/openai-primary-runtime/presentations/26.1111.10930/skills/presentations';
const BASE=path.resolve('1. 기획서 관련');
const BUILD=path.join(BASE,'작업자료');
const OUT=path.join(BASE,'산출물');
const PRE=path.join(BASE,'슬라이드 미리보기');
await Promise.all([BUILD,OUT,PRE].map(p=>fs.mkdir(p,{recursive:true})));
const C={navy:'#142B43',text:'#26384A',muted:'#586C7D',teal:'#087F83',pale:'#EAF6F4',line:'#D8E3E8',bg:'#FFFFFF',light:'#F3F6F8',green:'#16865D',orange:'#AF6508',red:'#BD3C41'};
const FONT='Malgun Gothic';
const P=Presentation.create({slideSize:{width:1280,height:720}});
let seq=0;
function box(s,x,y,w,h,fill=C.light,stroke='none',sw=0){return s.shapes.add({name:'shape-'+(++seq),geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:stroke,width:sw,style:'solid'}})}
function txt(s,t,x,y,w,h,size=24,color=C.text,bold=false,align='left'){
 let q=box(s,x,y,w,h,'none'); q.text=t;q.text.style={typeface:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:0};return q;
}
function rule(s,x,y,w,color=C.line,h=1){box(s,x,y,w,h,color)}
function tag(s,t,x,y,w=110,color=C.teal,fill=C.pale){box(s,x,y,w,30,fill);txt(s,t,x+10,y+3,w-20,24,16,color,true)}
function base(n,title,kicker,sub=''){
 const s=P.slides.add();s.background.fill=C.bg;
 txt(s,kicker,56,28,1080,26,17,C.teal,true);
 txt(s,title,56,75,1168,62,38,C.navy,true);
 if(sub)txt(s,sub,58,143,1164,52,22,C.muted);
 rule(s,56,674,1168);txt(s,'ROAD WATCH  /  2026.11.12  /  구현 전 기획 초안',56,689,1060,20,13,C.muted);txt(s,String(n).padStart(2,'0'),1166,684,58,28,19,C.navy,true,'right');
 return s;
}
function note(s,text,sources=[]){s.speakerNotes.text=text+'\n\n출처 및 확인 근거 (확인일 2026-11-12)\n'+sources.join('\n');}
function label(s,num,title,body,x,y,w,h=180){txt(s,num,x,y,w,44,32,C.teal,true);txt(s,title,x,y+56,w,37,26,C.navy,true);txt(s,body,x,y+108,w,h-92,23,C.text);}
function table(s,values,x,y,widths,rowH=73,font=21){
 let tb=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:widths.reduce((a,b)=>a+b,0),height:rowH*values.length,columnWidths:widths,values});
 tb.borders.assign({fill:C.line,width:1,style:'solid'});
 for(let r=0;r<values.length;r++){tb.rows[r].height=rowH;for(let c=0;c<values[0].length;c++){
  let z=tb.getCell(r,c);z.fill=r===0?C.navy:(r%2?C.light:C.bg);z.text.style={typeface:FONT,fontSize:font,bold:r===0,color:r===0?'#FFFFFF':C.text,verticalAlignment:'middle',autoFit:'none',insets:12};
 }}return tb;
}
function arrow(s,x,y,w=30){let a=box(s,x,y,w,22,C.teal);a.geometry='rightArrow';}
function placeholder(s,t,x,y,w,h){box(s,x,y,w,h,C.light,C.line,1.5);txt(s,'이미지 교체 영역',x+20,y+18,w-40,30,17,C.muted,true);txt(s,t,x+28,y+h/2-26,w-56,82,23,C.muted,false,'center');}
const U={ai:'https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&dataSetSn=197&topMenu=100',aip:'https://aihub.or.kr/intrcn/guid/usagepolicy.do',bdd:'https://raw.githubusercontent.com/bdd100k/bdd100k/master/doc/source/download.rst',bddlic:'https://raw.githubusercontent.com/bdd100k/bdd100k/master/doc/source/license.rst',kitti:'https://www.cvlibs.net/datasets/kitti/eval_tracking.php',kittip:'https://www.cvlibs.net/datasets/kitti/',culane:'https://xingangpan.github.io/projects/CULane.html',track:'https://docs.ultralytics.com/modes/track',dl:'https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.segmentation.deeplabv3_mobilenet_v3_large.html',android:'https://developer.android.com/develop/background-work/services/fgs/service-types',androidbg:'https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start',ios:'https://developer.apple.com/documentation/avfoundation/avcapturesession/interruptionreason/videodevicenotavailableinbackground',call:'https://developer.android.com/reference/android/content/Intent#ACTION_CALL',license:'https://www.ultralytics.com/license',privacy:'https://www.law.go.kr/법령/개인정보보호법'};

// 01: simple title and editable concept illustration
{
 let s=P.slides.add();s.background.fill='#FFFFFF';
 txt(s,'11월 컴퓨터 비전 AI 웹 서비스 기획서',56,37,1168,32,20,C.teal,true);
 txt(s,'ROAD WATCH',56,123,690,66,54,C.navy,true);
 tag(s,'프로젝트 가칭',59,202,143);
 txt(s,'AI 위험주행 감지·차량 추적\n증거 기록 및 신고 지원',56,264,720,138,40,C.navy,true);
 txt(s,'사람이 지정한 차량을 지속 추적하고,\n위험 의심 장면을 검토 가능한 기록으로 남깁니다.',59,425,692,84,25,C.muted);
 box(s,816,130,408,350,C.light,C.line,1);
 txt(s,'서비스 콘셉트',836,151,363,32,19,C.muted,true);
 box(s,923,224,179,131,'none',C.green,4);tag(s,'선택 차량 ID 27',923,190,179,C.green,C.pale);
 txt(s,'[전방 블랙박스 차량 추적\n화면 이미지 첨부 필요]',836,389,364,66,21,C.muted,false,'center');
 rule(s,56,553,1168);
 [['11.16','기획서 PDF + Context .md'],['11.30','학습 모델을 적용한 작동 MVP'],['12.22','2PC 관제 연동 발표·시연']].forEach((a,i)=>{let x=56+i*397;txt(s,a[0],x,578,350,40,29,C.teal,true);txt(s,a[1],x,628,360,30,20,C.text);});
 note(s,'현재는 구현 전 기획 단계다. 서비스의 장기 목적은 음주·졸음·난폭·보복운전 등에 따른 교통사고 감소를 돕는 것이다. 외부 주행영상만으로 운전자 상태나 고의성, 법 위반을 확정하지 않는다. 11월 16일 제출 PDF는 PPT 검토 후 사용자가 변환한다. 이번 산출물에는 제출 PDF를 만들지 않는다. 모든 일정은 2026년이다.',['사용자 확정 요구사항 (2026-11-12)','기존 기술 검토: AI_위험주행_차량추적_MVP_기획_8p.pdf, 1~8쪽']);
}
// 02
{
 let s=base(2,'문제 정의: 위험 상황을 봐도 기록을 정리하기 어렵습니다','01  문제 정의','위험을 발견한 시민이 안전하게 기록하고, 사후 검토에 필요한 근거를 모으는 문제');
 label(s,'01','대상 차량을 놓침','여러 차량이 겹치면\n관찰한 차량을 다시 찾기 어렵습니다.',58,230,350,230);
 label(s,'02','의심 장면을 다시 탐색','긴 영상에서 시각과 장면을\n찾고 잘라내는 작업이 필요합니다.',456,230,350,230);
 label(s,'03','맥락을 설명하기 어려움','한 장의 사진만으로는\n반복 이동과 차선 관계가 부족합니다.',854,230,350,230);
 box(s,56,511,1168,117,C.pale);txt(s,'컴퓨터 비전이 필요한 이유',78,531,1100,34,26,C.teal,true);txt(s,'차량의 위치·동일 ID·차선 경계를 시간에 따라 연결해야 의심 장면을 찾을 수 있습니다.',78,580,1100,32,23,C.text);
 note(s,'위 불편은 서비스 기획 가설이며 사용자 인터뷰로 확인해야 한다. AI가 선택 차량을 추적하고 차선과의 관계를 계산하면 단순 수기 입력이나 정지 이미지 검색으로 얻기 어려운 시간 맥락을 보조할 수 있다. 사고 감소 효과와 이용자 수요는 검증 전이다. 운전 중 조작과 위험 차량 추격을 유도하지 않는다.',['선생님 기획 지침 PDF, 1쪽: 문제 정의·비전 AI 도입 이유·UVP','사용자 확정 요구사항']);
}
// 03
{
 let s=base(3,'타겟 사용자와 핵심 가치','01  문제 정의','초기에는 보유 영상의 사후 검토로 효용을 검증하고, 모바일 사용은 이후 확장합니다.');
 const items=[['1차 사용자','블랙박스 영상을 보유한 시민','의심 장면의 대상과 시간을 정리\n차량 선택 후 이벤트 기록을 검토'],['확장 사용자','소규모 운행사업자 안전 담당자','여러 영상의 검토 부담을 완화\n필요한 장면과 판단 보류 사유 확인']];
 items.forEach((a,i)=>{let x=56+i*600;rule(s,x,223,568,C.teal,4);txt(s,a[0],x,248,568,30,19,C.teal,true);txt(s,a[1],x,300,568,42,30,C.navy,true);txt(s,a[2],x,365,568,110,25);});
 box(s,56,531,1168,97,C.light);txt(s,'효용 검증 가설',78,550,256,34,24,C.navy,true);txt(s,'동일 영상의 수동 검토 대비 정리 시간 30% 절감 목표\n사용자 5명 비교 평가 계획 · 사고 감소·지불 의사는 미검증',352,547,844,66,22,C.muted);
 note(s,'정량 효용 30% 절감은 제안 목표이며 실측 성과가 아니다. 사용자 5명이 동일 난이도의 영상에서 대상 확인, 이벤트 찾기, 클립 저장 작업을 수행하게 하고 수동 플레이어 대비 시간의 중앙값·정확성을 비교한다. 순서 효과를 줄이기 위해 유사 영상을 교차 배정한다. 오연결과 누락이 늘면 시간만 단축해도 성공으로 보지 않는다. 주 개발자는 본인 1명이고 팀원 1명은 아이디어 검토와 12월 최종 시연을 지원한다.',['사용자 요구 및 본 기획의 검증 가설']);
}
// 04
{
 let s=base(4,'전체 서비스 비전: 사람의 지정에서 검토 기록까지','02  서비스 범위','관찰한 행동을 기록합니다. 운전자의 상태·신원과 법적 판단은 서비스가 확정하지 않습니다.');
 [['사람의 판단','의심 차량 발견\n한 대를 직접 지정'],['AI 영상 분석','차량 검출·지속 추적\n차선과 시간 패턴 분석'],['증거 기록','장면·시각·분석 근거\n사용자가 확인 후 보관'],['모의 관제 연동','허가 영상에서 후보 탐색\n사람의 확인 후 연결']].forEach((a,i)=>{let x=56+i*300;box(s,x,237,268,171,i===1?C.pale:C.light);txt(s,a[0],x+18,258,235,38,27,C.navy,true);txt(s,a[1],x+18,321,235,68,21);if(i<3)arrow(s,x+274,310,20)});
 const rows=[['11월 필수','PC·로컬 웹에서 차량 추적 + 차선 학습 + 이벤트 기록'],['12월 고도화','2PC 데이터 전송 + CCTV 후보 재탐색 + 모의 신고'],['장기 비전','음성 호출·최대 10분 분석·내비 연동·정책 협력']];
 rows.forEach((a,i)=>{let y=455+i*57;txt(s,a[0],58,y,193,32,22,C.teal,true);txt(s,a[1],252,y,965,34,23);if(i<2)rule(s,58,y+43,1166)});
 note(s,'11월은 실제 영상 입력·선택·추적·학습 모델 적용·자동 이벤트·저장·평가가 작동하는 콘텐츠를 제출한다. 12월에는 11월 코드를 기반으로 두 컴퓨터를 연결한다. 장기적으로 음성 애칭 호출 뒤 분석을 최대 10분 수행하고 명확한 패턴이 없으면 대기 모드로 복귀하는 정책을 검토한다. 이벤트 없음은 정상운전의 증거가 아니다. 경찰 전용 협력 창구·관제부서 신설은 정책 협력 비전일 뿐 협약이나 접근 권한이 없다.',['사용자 확정 방향 및 일정']);
}
// 05
{
 let s=base(5,'핵심 사용자 여정과 예외 대응','03  UX/UI·와이어프레임','11월 시연은 운행 중 조작 없이, PC에서 허가된 전방 영상을 분석합니다.');
 [['01','영상 입력'],['02','정지 후 선택'],['03','추적·차선 분석'],['04','이벤트 검토'],['05','클립·기록 저장']].forEach((a,i)=>{let x=56+i*238;txt(s,a[0],x,219,211,38,25,C.teal,true);txt(s,a[1],x,266,211,36,24,C.navy,true);if(i<4)arrow(s,x+207,272,23)});
 const screens=[['입력 화면','[ 영상 파일 선택 / 드래그 ]','권한·이용 목적 확인\n길이·FPS·해상도 안내'],['분석 대기 화면','차량 검출  >  차선 분석  >  기록','진행률·취소 버튼\n느린 처리 시 예상 상태 안내'],['결과 확인 화면','[ 이벤트 목록 / 재생 / 저장 ]','판단 근거·신뢰도·보류 사유\n오탐 제외·대상 재선택']];
 screens.forEach((a,i)=>{let x=56+i*397;box(s,x,344,374,211,C.light,C.line,1);txt(s,a[0],x+18,360,339,34,24,C.navy,true);box(s,x+18,410,338,50,'#FFFFFF',C.line,1);txt(s,a[1],x+28,422,319,31,17,C.teal,true);txt(s,a[2],x+18,481,338,64,20);});
 txt(s,'와이어프레임 · 추적 상실 또는 차선 불명확 시 분석을 보류하고, 사용자 확인 뒤 재개',58,593,1155,41,22,C.muted);
 note(s,'시나리오: 영상 사용 권한 확인 → 로컬 업로드 → 검출된 차량 중 정지 화면에서 한 대 클릭 → 분석 진행 → 의심 이벤트와 근거 영상 확인 → 오탐 제외 또는 저장. 파일이 열리지 않거나 코덱·시간 정보가 불명확하면 이유를 안내한다. 재선택·뒤로 탐색·장면 전환 시 추적 상태와 이벤트 창을 초기화한다. 자동 분석과 수동 표시의 출처를 기록에 구분한다. 장기 모바일 UX는 사전 설정·음성 중심이고 위험 차량을 따라가라고 안내하지 않는다.',['선생님 기획 지침 PDF, 2쪽: 입력·분석 대기·결과 화면','사용자 요구사항']);
}
// 06
{
 let s=base(6,'메인 화면: 선택 차량과 위험 의심 근거를 함께 표시','03  UX/UI·와이어프레임','서비스 콘셉트 · 화면 예시의 이벤트 수와 상태는 가상 데이터입니다.');
 box(s,56,214,805,401,C.light,C.line,1);
 box(s,56,214,805,54,C.navy);txt(s,'TOTAL: 위험 의심 2 / 검토 필요 1',74,227,769,31,24,'#FFFFFF',true);
 txt(s,'[전방 영상에서 특정 차량을 추적하는\n실제 시연 화면 이미지 첨부 필요]',82,296,748,78,23,C.muted,false,'center');
 box(s,412,403,156,119,'none',C.orange,4);tag(s,'ID 27 · 검토',412,371,156,C.orange,'#FFF2DF');
 box(s,666,375,95,74,'none',C.green,3);txt(s,'ID 08',671,453,92,28,17,C.green,true);
 txt(s,'+차선 이탈 의심 1',80,418,305,40,24,C.orange,true);txt(s,'짧게 상승 후 사라짐 (연출 구상)',80,465,310,58,17,C.muted);
 rule(s,75,555,765);txt(s,'00:18 / 01:00      일시정지     재선택     이벤트 확인     저장',75,577,765,28,18,C.text);
 const cs=[['초록 · 추적 중','안전운전 확정 아님',C.green],['주황 · 추가 검토','이벤트 의심 또는 근거 확인',C.orange],['빨강 · 신고 검토','정의한 패턴 기준 충족\n법적 위반 확정 아님',C.red]];
 cs.forEach((a,i)=>{let y=228+i*111;box(s,901,y+5,11,25,a[2]);txt(s,a[0],928,y,287,34,24,a[2],true);txt(s,a[1],928,y+45,287,56,20,C.muted)});
 txt(s,'상실·불명확: 회색 + 판단 보류\n색상과 문구를 함께 표시',901,572,314,57,20,C.muted);
 note(s,'위험 의심 2는 자동 기준으로 집계된 고유 이벤트 2건, 검토 필요 1은 별도 근거 확인 대기 항목 1건이라는 UI 예시다. 집계 정의를 실제 구현 시 고정하고 같은 이벤트를 프레임마다 중복 카운트하지 않는다. 신호위반 의심 등 미래 이벤트는 11월 기본 메뉴에 비활성 확장 항목으로만 표기할 수 있으며 구현했다고 표현하지 않는다. 알림은 한 줄·짧은 노출로 제한하고 주행 중에는 애니메이션 최소화/끄기를 기본으로 검토한다. 신고 경쟁·보상·음향 효과는 넣지 않는다. 상태 색상은 법적 판단을 뜻하지 않는다. 빨강은 사전에 정의된 반복 패턴 기준을 충족한 신고 검토 단계다.',['사용자 확정 색상 의미·이벤트 UI 요구']);
}
// 07
{
 let s=base(7,'컴퓨터 비전 핵심: 지속 추적 + 학습한 차선 + 시간 규칙','04  AI·데이터 전략','차량 검출 사전학습 모델과 직접 학습할 차선 모델의 역할을 구분합니다.');
 table(s,[['처리 단계','11월 구현 선택','새로 만드는 핵심'],['차량 검출·추적','YOLO Nano 사전학습 + ByteTrack','선택 ID 고정·가림/상실·재선택'],['차선 인식','DeepLabV3-MobileNetV3 파인튜닝','차선/배경 2클래스 학습·경계 복원'],['시간 패턴 분석','OpenCV 기하 + 규칙 엔진','차선 대비 위치·반복 이동·판단 보류']],56,218,[226,472,470],72,21);
 box(s,56,530,563,111,C.pale);txt(s,'이벤트 기준 초안 · 검증 전 가설',75,544,525,34,24,C.teal,true);txt(s,'경계 교차 0.5초 지속: 차선 이탈 의심\n6초 내 3회 교대 접근: 반복 패턴 신고 검토',75,583,525,55,20);
 box(s,643,530,581,111,C.light);txt(s,'OpenCV 기준선과 학습 모델 비교',662,544,543,34,24,C.navy,true);txt(s,'주간·직선 우선, 자차 회전·차선 소실 시 보류\n색상·실선/점선은 검증한 속성만 표시',662,583,543,55,20);
 note(s,'[계획] YOLO는 car/bus/truck만 사용하고 모델 파일·해시·클래스명을 확인한다. ByteTrack을 기본선으로 명시적으로 선택하며 라이브러리 기본 tracker를 가정하지 않는다. 이동 카메라에서 BoT-SORT의 GMC 옵션을 비교할 수 있지만 3차원 자차 운동을 완전히 제거하지 못한다. tracker ID는 세션 내 임시 번호다. 선택 키=(session_id, track_id, selection_epoch). 가림/충돌 후보에서 임의 ID로 바꾸지 않고 HOLD, 상실이 길면 LOST 및 수동 재선택한다. 이전 위치의 외삽은 근거 영상처럼 표시하지 않는다.\n[계획] DeepLabV3-MobileNetV3의 사전학습 특징부를 사용하고 2클래스 차선 헤드를 실제 학습한다. 일반 segmentation 가중치는 차선 학습 완료 모델이 아니다. 차선은 얇으므로 배경 제외 lane IoU·Dice와 경계 F1을 본다. 실선/점선과 흰색/노란색은 데이터 속성을 보존해 조건별 성능을 비교하되, 11월 필수는 차선/배경 경계다. 속성 전용 학습은 라벨 수가 충분할 때만 확장한다.\n[계획/가설] 대상 박스 하단 중심의 y에서 같은 진행 방향 양쪽 차선 L(y),R(y)를 대응시켜 u=(x-L)/(R-L)를 계산한다. 박스는 접지점 근사라 가림·원근에 취약하다. 좌우 경계가 뒤바뀌거나 폭이 불안정하면 보류한다. 경계 교차가 0.5초 지속하면 이탈 의심 1건, 6초 안 좌우 경계 교대 접근 3회면 반복 이동 의심으로 신고 검토 후보(초기값). 2초 안정 복귀 후에만 재집계한다. 개발/validation에서 조정 후 test 전에 고정한다. 단순 차선 변경은 법 위반/음주로 해석하지 않는다. 자차 배경 optical flow·차선 공통 이동으로 회전/급이동을 감지하고 보류하며 마지막 차선·차량 대열은 보조 정보로만 쓴다.',['수업 코드: 02 DeepLearning/10 object_detection_video.py','수업: Computer Vision 실습 개요 소개.pdf 21쪽 (YOLO+ByteTrack)','수업 코드: 04 YOLO pose segmentation/03 YOLO Segmentation danger-zone.py',U.track,U.dl]);
}
// 08
{
 let s=base(8,'데이터 확보와 실제 파인튜닝 계획','04  AI·데이터 전략','공개 자료의 존재·라벨은 확인했습니다. 다운로드·사용 승인과 실제 품질 검사는 착수 전 과제입니다.');
 table(s,[['데이터 후보','확인된 라벨 / 활용','접근·권한 및 대안'],['AI Hub 차선/횡단보도\n수도권(197)·수도권 외(196)','차선 polyline + 색상 + 실선/점선\n1순위 차선 마스크 학습','본인 확인·신청 절차, 이용정책 준수\n국외 반출·외부 라벨링 전 별도 확인'],['BDD100K / KITTI Tracking','BDD: 차선 마스크·차량/추적 라벨\nKITTI: 박스·track ID, 추적 평가','BDD 교육·연구 조건, 상용 별도 검토\nKITTI 학술용, 다운로드 로그인'],['사용 허가 영상 직접 라벨링','차선 polyline·차량 ID·이벤트 구간\n국내 보정 + 잠금 테스트','공개 데이터 지연 시 작은 범위로 전환\n음주 정답 대신 관측 가능한 행동 라벨']],56,207,[319,432,417],79,19);
 txt(s,'600~1,200장 목표',58,548,358,35,26,C.teal,true);txt(s,'영상·주행 단위 70/15/15 분할\n인접 프레임·동일 노선 누출 방지',58,591,358,57,19);
 txt(s,'실제 학습·기록 보존',455,548,358,35,26,C.teal,true);txt(s,'20~40 epoch 범위·조기 종료\n가중치·설정·곡선·test 결과 제출',455,591,358,57,19);
 txt(s,'확보 실패 시 300장',852,548,372,35,26,C.teal,true);txt(s,'2클래스 학습·평가 자체는 유지\n표본 한계와 낮은 일반화 명시',852,591,372,57,19);
 note(s,'AI Hub 수도권 197과 수도권 외 196의 공식 페이지는 흰색/노란색/파란색, 실선/점선 속성과 polyline 좌표를 명시한다. 차선 중심선 annotation은 도색 전체의 픽셀 마스크와 다르므로 해상도 기준의 고정 두께로 rasterize하고 동일 평가 규칙을 쓴다. 색/종류 속성은 원본 metadata로 보존한다. 11월 학습은 차선 이진 segmentation이며 미학습 속성 모델을 학습했다고 쓰지 않는다. 원본 데이터 및 승인 조건을 확인한 뒤 사용한다. AI Hub 데이터의 국외 반출 및 제3자 제공 제한을 검토하므로 해외 클라우드·Roboflow에 원본을 임의 업로드하지 않는다. CVAT 로컬을 기본으로 하고 Roboflow는 본인 권리 영상의 비공개 프로젝트·지역/약관이 맞는 경우에만 선택한다.\nBDD100K는 detection, tracking, lane marking 자료가 서로 다른 task package이며 lane mask와 drivable area mask를 혼동하지 않는다. 공식 문서가 ETH 미러를 안내하지만 실제 다운로드 성공과 파일 정합성은 미확인이다. 코드 BSD와 데이터 라이선스는 별개다. KITTI는 공개 train sequence를 내부 clip 단위 분할해 평가하고 student project로 공식 test leaderboard 제출을 계획하지 않는다. CULane은 spline/차선위치 평가의 보조 후보이나 국내 색상/실선/점선 정답을 제공하는 것으로 가정하지 않는다. 가려진 차선의 문맥 annotation을 실제 관측 근거로 오해하지 않는다.\n목표 600~1,200 프레임은 실제 확보량 아님. 최소 12개 독립 주행 그룹을 목표로 70/15/15 분할하고 source manifest·촬영자·노선·주행일·해시를 기록한다. 증강은 train만, 유사 프레임/클립 중복 제거, 원본 split을 존중한다. 허가 영상 기반 fallback은 총 300장(예 210/45/45), 2클래스·주간 직선 범위로 축소하되 실제 학습은 유지한다. test 표본 부족 시 탐색 결과로만 보고한다.\n20~40 epoch 상한, 512×288 또는 640×360, BCE/CE+Dice 검토, 초기 encoder freeze 뒤 후반 unfreeze, validation 조기 종료, GPU 확인 후 batch 결정. 동일 split에서 OpenCV 기준선·학습 전/후를 비교. 이벤트 정답은 별도 20~40초 영상에 대상·시작/종료·자차 동작·관측 가능/보류를 표시하고 일부를 팀원이 교차 검토한다. 불일치는 보류. 위험 운전을 촬영하기 위해 연출하지 않는다.',[U.ai,'https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=196',U.aip,U.bdd,U.bddlic,U.kitti,U.kittip,U.culane]);
}
// 09
{
 let s=base(9,'기술 아키텍처: 로컬 웹과 Python 영상 처리','05  구현 구조','11월은 한 PC에서 실행합니다. 영상 추론은 브라우저가 아닌 로컬 Python 백엔드가 담당합니다.');
 const blocks=[['웹 UI','영상 업로드·정지 선택\n추적 오버레이·이벤트 검토\nReact + Vite'],['로컬 API / 작업 큐','session·selection 관리\n프레임·시각 동기화\nFastAPI'],['영상 분석 작업자','YOLO + ByteTrack\n차선 학습 모델 + 시간 규칙\nPyTorch + OpenCV']];
 blocks.forEach((a,i)=>{let x=56+i*397;box(s,x,225,367,224,i===2?C.pale:C.light,C.line,1);txt(s,a[0],x+20,245,328,39,28,C.navy,true);txt(s,a[1],x+20,311,328,117,23);if(i<2)arrow(s,x+372,324,20)});
 txt(s,'로컬 저장',58,493,230,37,27,C.teal,true);
 txt(s,'원본 참조 + 이벤트 전후 클립 + JSON/CSV + SQLite',300,493,906,42,27,C.navy,true);
 rule(s,56,550,1168);txt(s,'기록 필드',58,573,210,33,22,C.muted,true);txt(s,'영상 시각·선택 ID·이벤트 종류·근거·보류 사유·모델 버전\n번호판은 11월 수동 확인값 우선 · 색상·차종은 검증 시에만 “추정” 표시',300,572,906,71,22);
 note(s,'계획 스택: Python 3.11, torch/torchvision 호환 stable 조합, ultralytics, opencv-python, numpy, FastAPI, uvicorn, SQLite. 프론트는 Node 22 LTS 계열, React+Vite+TypeScript를 계획한다. 실제 설치 버전은 환경 점검 후 검증된 조합으로 lock한다. 최신 버전 호환을 추정해 기재하지 않는다. 시간이 부족하면 프론트를 최소 업로드·정지 캔버스·선택·재생 화면으로 줄이되 추적과 학습을 보존한다.\n학습 경로는 라벨→분할 manifest→학습→validation 선택→가중치→추론 worker이며 추론 때 학습하지 않는다. 서버 UI는 localhost만 바인딩하고 승인된 개발자 계정만 접근한다. 영상 timestamp는 원본 PTS를 사용하며 CFR 파일은 프레임/FPS로 검증한다. FPS가 없거나 VFR이면 변환/해석 정책을 명시하고 30fps를 임의 대입해 증거 시각으로 쓰지 않는다. 재생속도와 원본 시각을 구분한다. 이벤트 전5초/후5초를 기본으로 검토하고 시작/종료 경계 잘림을 표시한다.\n모델·라벨·실험과 증거 기록을 분리하고 UI에서 원본·분석 파생본을 구별한다. hash를 보존하지만 hash만으로 법적 증거능력을 보증하지 않는다. 기본 자동 외부 전송은 없다. 저장 실패·디스크 부족·업로드 코덱 실패를 안내한다. CPU/GPU fallback은 속도와 기능 차이를 공개한다.',['선생님 기획 지침 PDF, 2쪽: 실행 위치와 기술 스택','사용자 확정 범위 및 설계 제안']);
}
// 10
{
 let s=base(10,'11월 30일 MVP: 작동 영상과 학습·평가 근거 제출','06  실행 로드맵','아래 수치는 초기 합격 목표이며 현재 성능이 아닙니다. 미달 시 측정값과 실패 원인을 공개합니다.');
 table(s,[['필수 구현','검증 방법','초기 목표 / 제출 근거'],['차량 선택·지속 추적','보이는 정답 프레임에서 동일 대상·IoU≥0.5','유지율 ≥90%, ID 전환·상실 횟수 별도'],['차선 모델 실제 학습·인식','독립 test의 lane IoU·Dice·경계 F1','lane IoU ≥0.50, OpenCV 기준선과 비교'],['위험 의심 이벤트·3색 표시','정답 구간과 시간 IoU≥0.3, 1:1 매칭','Precision ≥0.80 / Recall ≥0.60'],['집계·클립·기록 저장','비사건 영상 오탐·중복 집계·재열기 확인','오탐 ≤0.2건/분, 저장 20/20 목표']],56,215,[305,474,389],70,20);
 box(s,56,587,1168,63,C.pale);txt(s,'필수 보존: 차량 추적 + 실제 차선 학습 + 자동 이벤트 1종     축소: OCR·신호·모바일·자동 발신',74,604,1130,32,22,C.teal,true);
 note(s,'평가 세부 정의: 차량 검출은 car/bus/truck 자체 bbox 정답에서 Precision, Recall, mAP50 및 mAP50-95를 보고한다. 작은 평가셋에서 mAP는 탐색값임을 명시한다. 추적 유지율=(동일 선택 차량에 IoU≥0.5로 맞은 프레임)/(선택 차량이 평가 가능하게 보이는 정답 프레임). 분석 보류 프레임을 임의로 분모에서 제거하지 않으며 전체 조건과 지원 조건별 성능을 둘 다 보고한다. ID switches·오연결·상실·수동 재선택을 별도로 집계한다. 차선은 배경 포함 accuracy가 아니라 lane 클래스 IoU≥0.50 초기 목표, Dice·경계 F1(고정 해상도에서 예 3px 허용)·색상/종류별 실패를 보고한다. 목표는 validation pilot 후 test 봉인 전에 고정한다.\n이벤트는 정답 시작/끝 구간과 시간 IoU≥0.3에서 1:1 matching. 하나의 정답에 중복 예측은 FP. P≥0.80,R≥0.60은 작은 표본용 목표이고 실도로 운영 성능을 의미하지 않는다. 잠금 test에서 패턴 양성 ≥10건과 비사건 영상 ≥10분을 목표로 한다. 정상 차선 변경·자차 회전·차선 소실·가림을 포함한다. 부족하면 수치와 분모를 공개하고 합격 판정을 보류한다. 보류율·이유와 분석 가능 시간 비율을 함께 제시해 abstention으로 성능을 부풀리지 않는다.\n처리 FPS·총시간/영상길이·사용 GPU/CPU·해상도·메모리도 측정한다. 11월은 영상 파일의 정확한 처리와 저장이 우선이고 실시간은 필수 합격 조건이 아니다. 최소 자동 기능은 차선 경계 교차 지속 의심 1종이며 반복 좌우 패턴은 조건을 충족하는 경우 확장한다. 차선 모델이 낮은 성능이어도 학습 결과·실제 추론·실패 사례를 제출하고 수동 이벤트를 자동인 것처럼 바꾸지 않는다. 색 3단계는 구현하되 빨강에 해당하는 사례를 확보하지 못하면 테스트용 모의 입력과 실제 분석 결과를 구분한다.',['사용자 11월 필수 요구','목표 수치는 본 기획 제안, 실측 전']);
}
// 11
{
 let s=base(11,'11월 개발 일정과 범위 조정 기준','06  실행 로드맵','2026.11.12 현재 기획 단계 · 주 개발 1명, 팀원 1명은 검토·최종 시연 지원');
 table(s,[['기간','핵심 작업','완료 증거 / 분기점'],['11.12~11.16','기획·자료 권한·환경 확인·라벨 규칙 확정','11/16 기획서 PDF + 초기 Context .md'],['11.17~11.20','영상 입력·차량 선택·ByteTrack·라벨 확보','선택 차량 추적 영상 / 11/18 데이터 대안 결정'],['11.21~11.24','차선 모델 학습·validation·OpenCV 비교','가중치·학습 곡선 / 이진 차선 학습은 유지'],['11.25~11.27','자동 이벤트 1종·3색·횟수·클립 저장','원본 시각과 이벤트·기록 재열기 확인'],['11.28~11.30','잠금 test·오류 분석·시연·제출','11/30 작동 MVP + 학습·평가·한계 보고']],56,216,[205,521,442],65,20);
 txt(s,'개발 가정: 11/17~30 약 55시간 + 버퍼 10시간 · 실제 가용시간·GPU는 확인 필요',58,631,1158,29,20,C.muted);
 note(s,'11/12~16은 기획·데이터 접근 확인이며 이번 요청에서 개발 코드는 작성하지 않는다. PDF 변환은 사용자가 PPT 검토한 뒤 진행한다. 11/17~30 55h 개발+10h 버퍼는 가용시간 가정이다. 예산 배분: 입력·선택·추적 15h, 데이터·차선 학습 18h, 이벤트·저장·UI 12h, 평가·문서·시연 10h. 데이터 확보와 학습은 앞당겨 실패 가능성을 줄인다. 11/18까지 AI Hub 접근/샘플 활용이 안 되면 권리 확보된 영상 300장 직접 라벨링 또는 조건이 맞는 BDD 차선 소규모 subset으로 전환한다. 11/24 학습·추적 불안정이면 속성 다중클래스·OCR·번호판 자동화·화려한 UI를 제거하고 이진 segmentation 실제 학습·선택 차량 추적·자동 이벤트 1종을 유지한다. 학습 자체를 12월로 미루지 않는다. 팀원은 아이디어 검토 및 정답 일부 교차 검토를 지원할 수 있으나 프로그램 개발은 본인이 맡는다.',['사용자 확정 제출일 (2026년)','개발시간은 계획 가정, 확정 일정 외 리소스 미확인']);
}
// 12
{
 let s=base(12,'12월 22일: 두 컴퓨터로 모의 관제 흐름 시연','07  12월 고도화','실제 경찰·CCTV 시스템 접속 없이, 허가된 영상과 로컬 네트워크로 연결합니다.');
 box(s,56,228,440,279,C.light,C.line,1);txt(s,'컴퓨터 1 · 분석 PC',78,248,398,41,30,C.navy,true);txt(s,'차량 지정·지속 추적\n위험 패턴·이벤트 클립 생성\n차량 특징과 기록 전송',78,319,398,113,25);
 arrow(s,528,338,190);txt(s,'LAN / API',528,283,190,34,23,C.teal,true,'center');txt(s,'event_id·시각\n특징·클립',528,390,190,61,20,C.muted,false,'center');
 box(s,752,228,472,279,C.pale,C.line,1);txt(s,'컴퓨터 2 · 모의 관제실',774,248,428,41,30,C.navy,true);txt(s,'웹 대시보드 수신·영상 확인\n별도 CCTV 영상의 후보 재탐색\n사람이 후보 선택 후 연결·추적',774,319,428,113,25);
 box(s,56,547,1168,96,C.light);txt(s,'실패해도 이어지는 시연',77,565,348,33,25,C.teal,true);txt(s,'번호판·색상만으로 동일 차량 확정 금지\n자동 매칭이 어려우면 후보 목록에서 사람이 연결하고, 근거·불확실성 기록',440,562,760,68,22);
 note(s,'12/1~7: 11월 오류 개선 및 PC 간 공통 event schema·인증 토큰·수신 API 구현. 12/8~14: 허가된 고정 CCTV/모의 CCTV 영상 준비, 차량 후보 검출과 후보 연결 UI. 12/15~19: 누락·전송 지연·중복 event_id·클립 재시도·ID 상실·시간대 정합성 개선. 12/20~22: 2PC 리허설, 최종 발표 및 시연.\n전송 구조 제안: event_id, source_session, selected_track_id, event_time, vehicle_color_estimate, vehicle_class_estimate, plate_text_optional, confidence, clip_reference/hash, reasons. PC1 track_id는 다른 카메라에서 유지되는 전역 ID가 아니므로 PC2에는 새 track_id와 association_id를 만들고 사람이 연결한 기록을 별도 저장한다. 흐릿한 번호판 OCR 결과는 공란/확인 필요로 둔다. 다른 시각·조명·관측 각도로 동일 차종 차량을 혼동할 수 있어 색·차종·번호판 후보와 시간/공간 맥락을 확인하고 확정하지 않는다. 모의 CCTV면 출처와 합성/재생임을 화면에 명시한다.\n신고 지원은 모의 음성 질문과 확인/취소 UI까지만 시연하고 실제 긴급전화는 발신하지 않는다. 네트워크 차단 시에는 로컬 전송 대기 및 재시도, 최후 fallback은 동일 JSON import를 사용하되 통신 성공인 것처럼 표현하지 않는다.',['사용자 12월 최종 목표 및 수동 후보 연결 대안']);
}
// 13
{
 let s=base(13,'오류·개인정보·신고의 경계','08  한계와 개선','판단을 멈추는 조건과 기록을 보호하는 정책을 기능으로 설계합니다.');
 table(s,[['위험 요소','MVP 대응','검증·개선 과제'],['가림·차선 소실·자차 회전','HOLD/LOST 표시, 자동 집계 중단\n대열·마지막 위치는 보조 정보만','야간·비·곡선은 별도 실패군\n보류율과 성능을 함께 보고'],['번호판·위치·증거영상 노출','로컬 접근 제한·공유용 마스킹\n얼굴 분석·차주 신원 조회 제외','촬영·이용 근거, 공유 범위 검토\n암호화·권한·접근 기록'],['보관·파기 누락','일반 기록 7일 후 삭제 정책 검토\n별도 보관은 사용자 지정','원본·클립·썸네일·DB 함께 파기\n백업·잠금 만료·삭제 확인 검증'],['잘못된 신고·자동 발신','사용자가 근거 검토·동의\n112 연결은 모의 UI로만 시연','긴급전화·스피커폰 OS 제약 확인\n관계 기관이 신원·법적 판단']],56,219,[274,447,447],81,21);
 txt(s,'7일은 법정 보관기간이 아닌 제품 정책 초안 · 사건 없음도 정상운전의 증거가 아님',58,644,1160,26,19,C.muted);
 note(s,'개인정보 처리의 구체적 법적 근거와 이동형 촬영 해당 여부는 서비스 운영 형태·촬영 목적·제공 방식에 따라 별도 검토해야 한다. 번호판은 다른 정보와 결합해 개인 식별이 가능하면 보호 대상이 될 수 있다는 전제로 최소 수집·권한·암호화·보관기간·공유 제한을 설계한다. 얼굴 분석·차주 조회는 하지 않는다. 공유용 얼굴/번호판 비식별화는 신원 추론과 분리된 보호 처리이며 기본 수동 검수/마스킹으로 시작한다. 얼굴 인식 모델은 쓰지 않는다. 원본은 제한된 로컬 저장, 공유본만 별도 파생한다.\n일반 기록 기본 7일은 제품 정책 가설이며 법정 기간이 아니다. 즉시 삭제, 사용자 보관 만료 지정·연장 확인, 파기 큐, 관련 DB·thumbnail·clip·임시 파일·백업 동기화와 파기 결과를 검토한다. 법령상 보존 등 예외는 운영 전에 검토하고 무기한 사용자 잠금을 기본값으로 두지 않는다. 이번에는 정책 설계이며 자동 파기 기능 구현·법률 검토 완료를 주장하지 않는다.\nAndroid Intent 공식 문서는 ACTION_CALL로 긴급전화 발신이 불가하고 ACTION_DIAL을 사용할 수 있다고 안내한다. 이 서비스에 자동 발신이나 스피커폰 제어 권한이 주어진다고 가정하지 않는다. 장기 음성 질문 “112에 신고할까요?”는 주황 이상에서 검토할 UX이며 사용자가 안전하게 동의/취소하도록 한다. 실제 구현은 긴급 상황 안내·사용자 통화 UI 연결 가능성을 따로 검증한다. 경찰 전용 협력 창구 신설은 장기 정책 비전이다.',[U.privacy,U.call,U.android]);
}
// 14
{
 let s=base(14,'장기 사업화: 모바일 기록과 독립 신고 모듈 확장','09  사업화 비전','기술·데이터 권리·사용자 효용을 확인한 뒤 단계별로 확장하는 사업 가설입니다.');
 txt(s,'모바일·내비 확장 비교',58,214,550,37,28,C.navy,true);
 table(s,[['경로','실현 조건 / 우선순위'],['자체 Android 앱','사용자가 화면에서 시작 + camera FGS\n권한·알림·제조사·발열 검증 우선'],['내비 내 기능·제휴','SDK·영상 접근 권리·사업 협의 필요\n통합 시에도 OS 정책 준수'],['부속 서비스 / iOS','영상 가져오기·사후 확인부터 가능\niOS 상시 백그라운드 카메라 가정 금지']],56,271,[186,405],76,19);
 txt(s,'독립 확장 기능',659,214,565,37,28,C.navy,true);
 txt(s,'객체 검출로 얻는 관측값',659,275,565,31,23,C.teal,true);
 txt(s,'차량·표지·소방시설·차선 후보 위치\n검출만으로 행위나 위법 여부를 확정할 수 없음',659,318,565,63,21);
 txt(s,'시간·맥락·사람 확인이 필요한 행위',659,402,565,31,23,C.teal,true);
 txt(s,'불법주차: 금지표지·구역·정차 시간·예외 확인\n투기·불법유턴·신호·갓길·버스차로: 연속 영상과 규정 확인',659,447,565,91,21);
 box(s,56,596,1168,57,C.pale);txt(s,'수익 가설: 개인 기록 구독 / 운행사업자 검토 도구     검증: 시간 절감·오탐 부담·유료 의사·라이선스 비용',73,612,1137,29,20,C.teal,true);
 note(s,'장기 모바일 시나리오: 사전 설정한 애칭을 음성으로 호출하면 최대 10분 분석, 명확한 패턴이 없으면 대기 복귀, 의심 이벤트는 근거와 함께 기록한다. 음성 상시 대기 자체도 마이크 권한·백그라운드 정책·전력 검증이 필요하다. Android는 camera foreground service의 권한/타입·시작 제약이 있어 앱이 보이는 상태에서 시작하는 흐름을 우선 실증한다. 제조사 절전 정책과 앱스토어 심사를 포함해 기종별 검증한다. 내비 기업이 특별 권한이나 카메라 스트림을 제공할 것이라고 가정하지 않는다. 내비 앱 내부 추가 기능은 기술 통합과 제휴 협의가 필요하며 독립 부속 앱이 내비 영상을 임의로 읽을 수 없다. iOS 일반 백그라운드 카메라는 제한되고 일부 멀티태스킹 조건은 일반 감시 앱의 허가를 의미하지 않는다. 초기 대안은 외부 블랙박스 파일 가져오기 또는 사용자 전경 세션이다.\n불법주차는 차선 분석과 별도 모듈이다. 노란 이중실선 후보, 금지표지/OCR, 소방시설 구역, 실제 정차 지속시간, 시간대·허용 예외를 결합하고 사람이 최종 확인한다. 이동 카메라의 한 번 통과 영상으로 장시간 정차를 증명할 수 없으므로 허가된 고정 영상/재방문 맥락이 필요하다. 투기는 물체·손·차량·궤적과 출처 확인, 신호는 신호색·정지선·차량 통과의 동기화, 유턴/갓길/버스차로는 구역·시간·예외를 요구한다. 작은 객체의 검출조차 실패할 수 있으므로 이를 검출 가능한 위반으로 표현하지 않는다.\n사업 가설은 개인용 기록/보관 구독 또는 B2B 영상 검토 도구다. 가격·시장 규모·공공기관 도입·사고 감소는 미검증. 사용자 인터뷰와 수동 검토 대비 시간·누락/오연결·재사용·유료 의사를 확인한다. 번호판 데이터 판매와 신고 건수 경쟁/보상은 수익 모델로 삼지 않는다. 비공개/상업 배포 전에 Ultralytics AGPL/Enterprise 선택과 데이터·학습 가중치 이용조건을 검토한다. 공공기관 협력은 협약 전까지 장기 비전이다.',[U.android,U.androidbg,U.ios,'https://developer.apple.com/documentation/avfoundation/avcapturesession/ismultitaskingcameraaccesssupported',U.license]);
}

await fs.writeFile(path.join(BUILD,'sources.json'),JSON.stringify(U,null,2),'utf8');
for(let i=0;i<P.slides.items.length;i++){
 let s=P.slides.items[i];let stem='slide-'+String(i+1).padStart(2,'0');
 let png=await P.export({slide:s,format:'png',scale:1});await fs.writeFile(path.join(PRE,stem+'.png'),new Uint8Array(await png.arrayBuffer()));
 let layout=await s.export({format:'layout'});await fs.writeFile(path.join(BUILD,stem+'.layout.json'),await layout.text());
 console.log('rendered',stem);
}
await fs.writeFile(path.join(BUILD,'presentation.json'),JSON.stringify(P.toProto()),'utf8');
const candidate=path.join(BUILD,'candidate.pptx');
await(await PresentationFile.exportPptx(P)).save(candidate);
const {finalizePresentation}=await import(pathToFileURL(SKILL+'/container_tools/artifact_tool_utils.mjs').href);
// Windows workspace may prohibit hardlinks while permitting ordinary copies.
// Preserve exclusive creation and the finalizer's post-publication SHA-256 check.
const originalLink=fs.link;
fs.link=async(source,dest)=>{try{return await originalLink(source,dest);}catch(e){if(process.platform==='win32'&&e.code==='EPERM')return await fs.copyFile(source,dest,fsConstants.COPYFILE_EXCL);throw e;}};
const result=await finalizePresentation({
workspaceDir:BASE,candidatePath:candidate,finalPath:path.join(OUT,'AI_위험주행_차량추적_11월_기획서_초안_v2.pptx'),
pythonExecutable:RT+'/python/python.exe',integrityValidatorPath:SKILL+'/container_tools/inspect_presentation_package_integrity.py',layoutValidatorPath:SKILL+'/container_tools/inspect_presentation_layout_geometry.py',
layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...[7,8,10,11,13,14].flatMap(n=>['--require-native-table-slide',String(n)])],explicitTotalSlideCount:14,
requiredNativeTableOwnerSlides:[7,8,10,11,13,14],fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,
receiptPath:path.join(BUILD,'presentation_v2.validation.json')});
console.log(JSON.stringify({finalPath:result.finalPath,receiptPath:result.receiptPath,sha256:result.finalSha256,package:result.packageIntegrity.status,layoutFindings:result.presentationLayout.findingCount,warnings:result.presentationLayout.warnings,importPassed:result.firstPartyImport.passed}));
