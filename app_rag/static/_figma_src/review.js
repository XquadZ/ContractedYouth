const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const samples=window.CONTRACT_SAMPLES;let selected=0,page=1,zoom=100,tab='risks',filter='all',customFile=null,customUrl=null;
let activeRiskId=null,pendingDocumentFocus=false,activeDocumentId=null;
const uploadedDocuments=[];
const answers=new Set();const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const data=()=>samples[selected];const risks=()=>data().risks;
function toast(t){$('#toast').textContent=t;$('#toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').classList.remove('show'),2500)}
function source(p,label='원문 보기',riskId=null){return `<button class="source" data-page="${p}" ${riskId?`data-risk-source="${riskId}"`:""}>▤ ${esc(label)} · ${p}쪽 ↗</button>`}
function riskBadge(r){return `<span class="badge ${r.level==='high'?'high':r.level==='info'?'neutral':'warn'}">${r.level==='high'?'우선 확인':r.level==='info'?'참고':'확인 필요'}</span><span class="badge ok">원본 참고</span>`}
function selectSample(i){selected=i;page=1;zoom=100;filter='all';activeRiskId=null;pendingDocumentFocus=false;customFile=null;customUrl=null;activeDocumentId=null;$('#jumpNotice').textContent='';drawList();drawViewer();render();$('#reportBody').scrollTop=0}
function drawList(){$('#sampleList').innerHTML=samples.map((s,i)=>`<button class="sample ${i===selected&&!customFile?'active':''}" data-sample="${i}" aria-pressed="${i===selected&&!customFile}"><span class="file-icon">▤</span><span><b>${esc(s.short)}</b><small>${s.count}쪽 · ${i===2?'기입된 계약':'표준 양식'}</small></span><span class="num">0${i+1}</span></button>`).join('');$('#sampleList').insertAdjacentHTML('beforeend',uploadedDocuments.length?'<div class="uploaded-list-label">업로드한 계약서</div>'+uploadedDocuments.map(d=>`<button class="sample uploaded-document ${activeDocumentId===d.id?'active':''}" data-document="${d.id}" aria-pressed="${activeDocumentId===d.id}"><span class="file-icon">▤</span><span><b>${esc(d.file.name)}</b><small>${(d.file.size/1024/1024).toFixed(2)} MB · 분석 대기</small></span></button>`).join(''):'');$$('[data-sample]').forEach(b=>b.onclick=()=>selectSample(+b.dataset.sample));$$('[data-document]').forEach(b=>b.onclick=()=>selectDocument(b.dataset.document))}
function drawViewer(){document.dispatchEvent(new Event("contract-view-change"));const s=data();$('#contractTitle').textContent=customFile?customFile.name:s.name;$('#contractDesc').textContent=customFile?'내 계약서 · 새 분석 워크스페이스':s.subtitle;$('#pageCount').textContent=customFile?'로컬 PDF':`${s.count} pages`;$('#pageCanvas').hidden=!!customFile;$('#highlightLegend').hidden=!!customFile;$('#customPdf').hidden=!customFile;$('#pageStrip').hidden=!!customFile;$('#pageNumber').textContent=customFile?'PDF':`${page} / ${s.count}`;$('#prev').disabled=!!customFile||page===1;$('#next').disabled=!!customFile||page===s.count;$('#zoomOut').disabled=!!customFile||zoom<=60;$('#zoomIn').disabled=!!customFile||zoom>=180;$('#pdfLink').href=customFile?customUrl:`assets/contracts/${s.id}.pdf`;$('#zoomValue').textContent=zoom+'%';if(customFile){$('#customPdf').src=customUrl;return}$('#customPdf').removeAttribute('src');$('#pageImage').src=`assets/contracts/${s.id}-${page}.jpg`;$('#pageImage').alt=`${s.name} 원본 ${page}쪽`;$('#pageCanvas').style.width=zoom+'%';drawHighlights();$('#pageStrip').innerHTML=Array.from({length:s.count},(_,i)=>`<button data-view-page="${i+1}" class="${page===i+1?'active':''}" aria-label="원본 ${i+1}쪽" aria-current="${page===i+1?'page':'false'}">${i+1}</button>`).join('');$$('[data-view-page]').forEach(b=>b.onclick=()=>jump(+b.dataset.viewPage,false))}
function jump(p,explain=true){if(customFile)return;page=p;drawViewer();$('#pageStage').scrollTo({top:0,left:0});$('#jumpNotice').textContent=explain?`${p}쪽 원문으로 이동했어요`:'';if(matchMedia('(max-width:850px)').matches&&explain)document.querySelector('.document-pane').scrollIntoView({behavior:'smooth',block:'start'})}
function overview(){const s=data(),done=s.checks.filter(c=>c[3]).length,rs=risks();return `<span class="section-kicker">YOUR CONTRACT, AT A GLANCE</span><h2>서명 전, 함께 확인해봐요.</h2><p class="muted">${esc(s.profile)}</p><div class="summary-state"><div class="ring">확인</div><div><b>${6-done}개 작성·조건 항목을 살펴보세요</b><p>필수 확인 목록 6개 중 문장·기입 확인 ${done}개<br>계약의 안전성을 점수로 판정한 결과는 아니에요.</p></div></div><div class="metrics"><div class="metric"><b>${done}/6</b><span>확인 목록 충족</span></div><div class="metric warn"><b>${rs.filter(r=>r.level==='check').length}</b><span>원본 확인 포인트</span></div><div class="metric red"><b>${rs.filter(r=>r.evidence?.length).length}</b><span>법률 근거 연결 항목</span></div></div><div class="section-label">계약 핵심 정보 <button data-open-tab="complete">미충족 항목 보기 →</button></div><div class="info-grid">${s.fields.map(f=>`<div><small>${esc(f[0])}</small><b class="${/필요/.test(f[1])?'blank':''}">${esc(f[1])}</b></div>`).join('')}</div><div class="insight"><span>✧</span><div><b>내 계약, 이렇게 읽어보세요</b><p>${esc(s.insight)}</p></div></div><div class="section-label">먼저 확인하면 좋은 내용 <button data-open-tab="risks">전체 보기 →</button></div>${s.risks.slice(0,2).map(r=>`<button class="quick" data-page="${r.page}"><span>●</span>${esc(r.title)}<span>${r.page}쪽 ↗</span></button>`).join('')}`}
function complete(){const missing=data().checks.filter(c=>!c[3]);return `<span class="section-kicker">COMPLETENESS CHECK</span><h2>필수 조항 완결성 검사</h2>${missing.length?`<p class="muted">미충족·추가 확인이 필요한 <b>${missing.length}개 항목만</b> 표시합니다. 충족한 항목의 내용은 표시하지 않아요.</p>${missing.map(c=>`<article class="check-row"><div class="check-top"><b>○ &nbsp; ${esc(c[0])}</b><span class="badge warn">작성·조건 확인</span></div><p>${esc(c[2])}</p>${source(c[1],c[4])}</article>`).join('')}`:'<div class="complete-success" role="status">✓ 필수 확인 목록에서 미충족 항목이 없어요.</div>'}`}

function evidenceBlock(r){return `<section class="legal-evidence"><div class="legal-title">⚖ 관련 법률 · 검토 근거</div>${r.evidence.map(e=>`<div class="legal-ref"><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)} ↗</a><p>${esc(e.summary)}</p><div class="legal-connection"><b>이 조항과 연결되는 이유</b><p>${esc(e.connection)}</p></div></div>`).join('')}<small>출처: 국가법령정보센터<br>관련 규정의 존재가 해당 계약의 위법성을 곧바로 의미하지는 않습니다.</small></section>`}
function riskCard(r){return `<article class="risk ${activeRiskId===r.id?'risk-selected':''}" id="risk-${r.id}" tabindex="-1"><div class="risk-top">${riskBadge(r)}<span style="font-size:9px;color:#a0abc0">${esc(r.clause)}</span></div><h3>${esc(r.title)}</h3><blockquote>${esc(r.quote)}</blockquote><p>${esc(r.explain)}</p>${source(r.page,"원문 보기",r.id)}${evidenceBlock(r)}<details><summary>수정·협의 방향과 확인 질문</summary><div class="suggestion"><strong>✧ 협의 방향</strong><p>${esc(r.suggest)}</p></div><p><b>물어볼 질문</b><br>${esc(r.question)}</p></details></article>`}
function riskView(){const rs=risks();return `<div class="review-summary"><div><span class="section-kicker">검토 결과</span><h2>위험 조항 필터링</h2></div><span class="result-total">총 ${rs.length}건</span></div><p class="muted compact-intro">원문의 색상 표시를 누르면 해당 검토 항목으로 이동해요.</p><div class="filters" aria-label="위험 조항 필터">${[['all','전체'],['high','우선 확인'],['check','확인 필요'],['info','참고']].map(([id,label])=>`<button data-filter="${id}" class="${filter===id?'active':''}" aria-pressed="${filter===id}">${label} ${rs.filter(r=>id==='all'||r.level===id).length}</button>`).join('')}</div>${[['high','우선 확인 사항'],['check','추가 확인 사항'],['info','참고 사항']].filter(([level])=>filter==='all'||filter===level).map(([level,label])=>{const items=rs.filter(r=>r.level===level);return items.length?`<details class="risk-group ${level}" open><summary><span class="status-dot"></span>${label}<b>${items.length}</b><span class="chevron">⌃</span></summary><div class="risk-group-body">${items.map(riskCard).join('')}</div></details>`:''}).join('')||'<div class="empty">해당하는 확인 항목이 없어요.</div>'}`}
function questions(){return `<span class="section-kicker">BEFORE YOU SIGN</span><h2>계약 전에, 이렇게 물어보세요.</h2><p class="muted">상대방과 확인할 질문을 모았어요.<br>확인한 질문에 체크하고 텍스트 리포트로 보관할 수 있어요.</p>${risks().map((r,i)=>{const key=data().id+':'+r.title;return `<article class="question"><span class="badge neutral">원본 관련 질문</span><b style="margin-top:10px">${esc(r.question)}</b><div><label class="${answers.has(key)?'done':'muted'}"><input type="checkbox" data-answer="${esc(key)}" ${answers.has(key)?'checked':''}> 확인했어요</label><button data-copy="${i}">질문 복사</button></div></article>`}).join('')}`}
function customReport(){return `<span class="section-kicker">내 계약서</span><h2>분석 워크스페이스</h2><div class="document-status"><span>◷</span><div><b>분석 대기</b><p>${esc(customFile.name)}</p></div></div><div class="custom-note">원본 PDF를 확인할 수 있어요. 실제 AI 분석 서버가 연결되면 이 문서의 필수 조항 검사와 위험 조항 검토 결과가 여기에 표시됩니다.</div><div class="pending-checks"><div>필수 조항 완결성 검사 <span>대기</span></div><div>위험 조항 필터링 <span>대기</span></div><div>관련 법률·검토 근거 <span>대기</span></div></div>`}
function render(){let content;if(customFile)content=customReport();else content=({overview,complete,risks:riskView,questions}[tab])();$('#reportBody').innerHTML=content;$$('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-current',b.dataset.tab===tab?'page':'false')});$$('[data-page]').forEach(b=>b.onclick=()=>b.dataset.riskSource?focusDocumentRisk(b.dataset.riskSource):jump(+b.dataset.page));$$('[data-open-tab]').forEach(b=>b.onclick=()=>openTab(b.dataset.openTab));$$('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;const pos=$('#reportBody').scrollTop;render();$('#reportBody').scrollTop=pos});$$('[data-answer]').forEach(b=>b.onchange=()=>{b.checked?answers.add(b.dataset.answer):answers.delete(b.dataset.answer);b.parentElement.className=b.checked?'done':'muted'});$$('[data-copy]').forEach(b=>b.onclick=async()=>{try{await navigator.clipboard.writeText(risks()[+b.dataset.copy].question);toast('질문을 복사했어요.')}catch{toast('브라우저에서 복사가 지원되지 않아요. 질문을 선택해 복사해주세요.')}});$$('[data-reference]').forEach(b=>b.onclick=()=>selectSample(+b.dataset.reference))}
function openTab(t){tab=t;filter='all';render();$('#reportBody').scrollTop=0}
$$('[data-tab]').forEach(b=>b.onclick=()=>openTab(b.dataset.tab));$('#prev').onclick=()=>jump(page-1,false);$('#next').onclick=()=>jump(page+1,false);$('#zoomOut').onclick=()=>{zoom-=20;drawViewer()};$('#zoomIn').onclick=()=>{zoom+=20;drawViewer()};
function selectDocument(id){const d=uploadedDocuments.find(d=>d.id===id);if(!d)return;activeDocumentId=id;customFile=d.file;customUrl=d.url||(d.url=URL.createObjectURL(d.file));page=1;zoom=100;activeRiskId=null;pendingDocumentFocus=false;$('#jumpNotice').textContent='';drawList();drawViewer();render();$('#reportBody').scrollTop=0}
const documentStore=new Promise(resolve=>{if(!window.indexedDB){resolve(null);return}const request=indexedDB.open('youth-contract-workspaces',1);request.onupgradeneeded=()=>request.result.createObjectStore('documents',{keyPath:'id'});request.onsuccess=()=>resolve(request.result);request.onerror=()=>resolve(null)});
const restoredDocuments=documentStore.then(db=>new Promise(resolve=>{if(new URLSearchParams(location.search).get('tour')==='1'){resolve();return}if(!db){resolve();return}const request=db.transaction('documents').objectStore('documents').getAll();request.onsuccess=()=>{for(const d of request.result)uploadedDocuments.push(d);drawList();resolve()};request.onerror=()=>resolve()}));
async function receiveFile(file){if(!(file instanceof File))return;if(!/\.pdf$/i.test(file.name)||file.size>20*1024*1024||!file.size){toast('비어 있지 않은 20MB 이하의 PDF를 선택해주세요.');return}const header=new TextDecoder().decode(await file.slice(0,1024).arrayBuffer());if(!header.includes('%PDF-')){toast('올바른 PDF 파일을 선택해주세요.');return}await restoredDocuments;const d={id:crypto.randomUUID(),file,createdAt:Date.now()};uploadedDocuments.push(d);selectDocument(d.id);$('#upload').value='';const db=await documentStore;if(db){try{const tx=db.transaction('documents','readwrite');tx.objectStore('documents').put({id:d.id,file:d.file,createdAt:d.createdAt});tx.onerror=()=>toast('저장 공간이 부족해 현재 화면에서만 유지됩니다.')}catch{toast('현재 화면에서만 문서를 유지합니다.')}}toast('새 분석 워크스페이스에 계약서를 추가했어요.')}
$('#upload').onchange=e=>receiveFile(e.target.files[0]);window.addEventListener('message',e=>{if(e.source!==parent||e.origin!==location.origin)return;if(e.data?.type==='contract-review-file')receiveFile(e.data.file)});
$('#close').onclick=()=>{if(parent!==window){parent.postMessage({type:'contract-review-close'},location.origin)}else location.href='index.html#start'};
$('#export').onclick=()=>{if(customFile){toast('직접 연 문서에는 생성된 분석 리포트가 없어요.');return}const s=data();const text=`(계)약한청년들 | ${s.name}\n\n미리 작성한 샘플 리포트입니다. 실제 AI 분석이나 법적 판단이 아닙니다.\n원본 PDF: ${s.filename}\n\n[미충족·추가 확인 항목]\n`+s.checks.filter(c=>!c[3]).map(c=>`[작성·조건 확인] ${c[0]} / ${c[1]}쪽\n${c[2]}`).join('\n\n')+'\n\n[위험 항목 및 관련 법률]\n'+risks().map(r=>`[원본 참고] ${r.title}\n${r.quote}\n${r.explain}\n관련 법률: ${r.evidence.map(e=>e.title+" / "+e.url+" / "+e.connection).join("\n")}\n확인 질문: ${r.question}\n확인 여부: ${answers.has(s.id+':'+r.title)?'확인함':'미확인'}\n참고 원문: ${r.page}쪽`).join('\n\n');const url=URL.createObjectURL(new Blob(['\ufeff'+text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`계약검토_${s.short}_샘플.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);toast('리포트를 저장했어요.')};

function drawHighlights(){
 const layer=$('#highlightLayer');layer.replaceChildren();if(customFile)return;
 risks().filter(r=>r.page===page).forEach(r=>(r.highlights||[]).forEach((rect,i)=>{
  const mark=document.createElement('button');mark.type='button';mark.className='pdf-highlight '+r.level+(activeRiskId===r.id?' selected':'');
  mark.dataset.highlightRisk=r.id;mark.style.cssText=`left:${rect.x}%;top:${rect.y}%;width:${rect.width}%;height:${rect.height}%`;
  const level=r.level==='high'?'빨강 · 우선 확인':r.level==='info'?'초록 · 참고':'노랑 · 확인 필요';
  mark.setAttribute('aria-label',level+' · '+r.title+' · 오른쪽 검토 항목 보기');mark.setAttribute('aria-pressed',activeRiskId===r.id);mark.title=level+' | '+r.title;
  mark.onclick=()=>focusReportRisk(r.id);layer.append(mark);
 }));
}
function focusReportRisk(id){
 const risk=risks().find(r=>r.id===id);if(!risk)return;
 activeRiskId=id;tab='risks';filter='all';render();drawHighlights();
 const card=document.getElementById('risk-'+id),body=$('#reportBody');
 if(card){
  card.focus({preventScroll:true});
  if(matchMedia('(max-width:850px)').matches)card.scrollIntoView({behavior:'smooth',block:'start'});
  else body.scrollTo({top:body.scrollTop+card.getBoundingClientRect().top-body.getBoundingClientRect().top-12,behavior:'instant'});
 }
 $('#jumpNotice').textContent='선택한 조항의 검토 근거를 표시했어요';
}
function scrollToHighlight(){
 if(!pendingDocumentFocus)return;
 const mark=[...$('#highlightLayer').children].find(n=>n.dataset.highlightRisk===activeRiskId);if(!mark)return;
 const stage=$('#pageStage'),mr=mark.getBoundingClientRect(),sr=stage.getBoundingClientRect();
 stage.scrollTo({top:stage.scrollTop+mr.top-sr.top-stage.clientHeight*.35,left:Math.max(0,stage.scrollLeft+mr.left-sr.left-stage.clientWidth*.2),behavior:'smooth'});
 pendingDocumentFocus=false;
}
function focusDocumentRisk(id){
 const risk=risks().find(r=>r.id===id);if(!risk)return;
 const reportPosition=$('#reportBody').scrollTop;activeRiskId=id;page=risk.page;pendingDocumentFocus=true;drawViewer();render();$('#reportBody').scrollTop=reportPosition;
 $('#jumpNotice').textContent=risk.page+'쪽의 관련 문장을 강조했어요';
 if($('#pageImage').complete)requestAnimationFrame(scrollToHighlight);
 if(matchMedia('(max-width:850px)').matches)document.querySelector('.document-pane').scrollIntoView({behavior:'smooth',block:'start'});
}
$('#pageImage').addEventListener('load',()=>{drawHighlights();scrollToHighlight()});

const initial=new URLSearchParams(location.search).get('sample');const n=samples.findIndex(s=>s.id===initial);selectSample(n<0?0:n);

const initialTab=new URLSearchParams(location.search).get("tab");if(["overview","complete","risks","questions"].includes(initialTab))openTab(initialTab);

// The landing page's embedded feature tour drives the existing review UI.
if(new URLSearchParams(location.search).get('tour')==='1'){
 window.addEventListener('message',e=>{
  if(e.source!==parent||e.origin!==location.origin||e.data?.type!=='contract-tour-step')return;
  const step=e.data.step;if(![0,1,2].includes(step))return;
  selectSample(step);
  openTab(['overview','complete','risks'][step]);
  if(step===2){focusReportRisk(data().risks[0].id);focusDocumentRisk(data().risks[0].id);}

 });
}
