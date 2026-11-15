/* Local sample conversation. No file or message is sent to a server. */
(() => {
  const histories = new Map();
  const log = document.getElementById('chatMessages');
  const input = document.getElementById('chatInput');
  let context = '';
  const key = () => customFile ? 'local:' + activeDocumentId : data().id;
  function welcome() {
    if (customFile) return {role:'assistant', text:'새 계약서 워크스페이스가 만들어졌어요. 원본 PDF는 확인할 수 있으며 분석은 대기 중입니다. 실제 AI 연결 전에는 이 문서에 대한 분석 답변을 생성할 수 없어요.'};
    const s = data(), missing = s.checks.filter(c => !c[3]);
    return {role:'assistant', text:`「${s.name}」의 검토 내용을 확인하세요.\n\n• 미충족·추가 확인 항목 ${missing.length}개\n• 위험·참고 조항 ${s.risks.length}개\n\n궁금한 조항을 질문해보세요. 답변의 ‘관련 조항 보기’를 누르면 원본과 검토 결과를 함께 확인할 수 있어요.`, action:'complete', label:'필수 조항 확인하기'};
  }
  function draw() {
    log.replaceChildren();
    for (const m of histories.get(context) || []) {
      const row = document.createElement('div'); row.className = 'chat-message ' + m.role;
      const name = document.createElement('span'); name.className='chat-author';name.textContent=m.role==='user'?'나':'AI 계약서 파트너';
      const bubble=document.createElement('div');bubble.className='chat-bubble';bubble.textContent=m.text;
      row.append(name,bubble);
      if(m.action){const b=document.createElement('button');b.className='chat-source';b.textContent=m.label||'관련 조항 보기 ↗';b.onclick=()=>m.action==='complete'?openTab('complete'):focusDocumentRisk(m.action);bubble.append(document.createElement('br'),b);}
      log.append(row);
    }
    log.scrollTop=log.scrollHeight;
  }
  function sync() {
    const next=key();document.getElementById('chatContract').textContent=customFile?customFile.name:data().short;
    if(next===context)return;
    context=next;input.value='';
    if(!histories.has(context))histories.set(context,[welcome()]);
    draw();
  }
  function reply(question) {
    if(customFile)return welcome();
    const s=data();
    if(/필수|빠진|누락|완결|빈칸/.test(question)) {
      const missing=s.checks.filter(c=>!c[3]);
      return {role:'assistant',text:missing.length?`추가 확인이 필요한 항목은 ${missing.length}개예요.\n\n${missing.map(c=>`• ${c[0]} (${c[1]}쪽)\n${c[2]}`).join('\n\n')}`:'필수 확인 목록에서 미충족 항목이 없어요.',action:'complete',label:'미충족 항목 보기 ↗'};
    }
    if(/위험|주의|요약|정리|검토/.test(question))return {role:'assistant',text:`이 계약서의 확인 포인트예요.\n\n${s.risks.map(r=>`• ${r.title} (${r.page}쪽)`).join('\n')}\n\n원본과 실제 합의 내용을 함께 확인해주세요.`,action:s.risks[0]?.id};
    const words=question.replace(/[?？.,]/g,' ').split(/\s+/).filter(w=>w.length>1);
    const ranked=s.risks.map(r=>({r,score:words.reduce((n,w)=>n+([r.title,r.clause,r.quote,r.explain,r.question].join(' ').includes(w)?1:0),0)})).sort((a,b)=>b.score-a.score);
    const match=ranked[0];
    if(match?.score){const r=match.r;return {role:'assistant',text:`${r.title}\n\n원문: “${r.quote}”\n\n${r.explain}\n\n관련 법률: ${r.evidence.map(e=>e.title).join(', ')}\n\n확인할 질문: ${r.question}`,action:r.id};}
    return {role:'assistant',text:'이 질문에 대한 답변은 준비되어 있지 않아요.\n\n‘필수 조항에서 빠진 내용을 알려줘’ 또는 ‘위험 조항을 정리해줘’를 선택하거나, 오른쪽 조항 제목에 있는 단어로 질문해보세요.'};
  }
  function send(text){const q=text.trim();if(!q)return;sync();const messages=histories.get(context);messages.push({role:'user',text:q},reply(q));input.value='';draw();input.focus({preventScroll:true});}
  document.getElementById('chatForm').onsubmit=e=>{e.preventDefault();send(input.value)};
  input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send(input.value)}});
  document.querySelectorAll('[data-chat-prompt]').forEach(b=>b.onclick=()=>send(b.dataset.chatPrompt));
  document.getElementById('chatReset').onclick=()=>{histories.set(context,[welcome()]);draw()};
  document.addEventListener('contract-view-change',sync);
  document.addEventListener('contract-tour-chat',()=>{histories.set(key(),[welcome()]);context=key();send('위험 조항을 정리해줘')});
  sync();
})();
