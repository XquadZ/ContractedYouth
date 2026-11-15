(() => {
 const steps=[['요약','계약의 핵심 정보를 한눈에 확인해요.','주택임대차 계약의 주요 조건과 확인 항목을 모아, 서명 전에 살펴볼 내용을 빠르게 파악할 수 있어요.'],['필수 조항','빠진 조항과 작성할 내용을 확인해요.','민간임대주택 계약에서 미충족하거나 추가 확인이 필요한 항목만 보여드려요. 충족한 항목은 표시하지 않아요.'],['위험 조항','주의할 문장과 검토 근거를 함께 살펴봐요.','부동산 매매계약서의 확인할 표현을 색으로 표시하고, 관련 법률과 수정·협의 방향을 연결해 보여드려요.']];
 document.querySelectorAll('contract-tour').forEach((host,index)=>{
  host.innerHTML=`<div class="tour-shell"><div class="tour-screen"><div class="tour-browser"><span class="tour-lights">● ● ●</span><span>(계)약한청년들 · 계약 검토</span><span class="tour-live">자동 시연</span></div><div class="tour-viewport"><iframe title="계약서 검토 기능 자동 시연 ${index+1}" src="/static/review.html?v=contract-slides-3&sample=housing&tab=overview&tour=1" tabindex="-1" loading="lazy"></iframe><div class="tour-pointer" aria-hidden="true">➤<span>위험 조항 선택</span></div></div></div><div class="tour-slide-description"><span class="tour-slide-label"></span><h3></h3><p></p></div><div class="tour-pagination"><div class="tour-dots" role="tablist" aria-label="기능 시연 화면 선택">${steps.map((step,i)=>`<button type="button" role="tab" data-tour-step="${i}" aria-label="${i+1}번 화면 · ${step[0]}" aria-selected="${i===0}" title="${step[0]}"><span></span></button>`).join('')}</div><span class="tour-status sr-only" aria-live="polite"></span></div></div>`;
  const frame=host.querySelector('iframe'),viewport=host.querySelector('.tour-viewport'),pointer=host.querySelector('.tour-pointer');
  let current=0,playing=!matchMedia('(prefers-reduced-motion: reduce)').matches,visible=false,timer;
  function size(){const scale=viewport.clientWidth/1440;frame.style.transform=`scale(${scale})`;viewport.style.height=(820*scale)+'px';}
  new ResizeObserver(size).observe(viewport);
  function send(){frame.contentWindow?.postMessage({type:'contract-tour-step',step:current},new URL(document.baseURI).origin)}
  function draw(){host.dataset.step=current;host.querySelectorAll('[data-tour-step]').forEach(b=>{b.setAttribute('aria-selected',+b.dataset.tourStep===current);b.tabIndex=+b.dataset.tourStep===current?0:-1;b.classList.toggle('active',+b.dataset.tourStep===current)});host.querySelector('.tour-status').textContent=steps[current][0];host.querySelector('.tour-slide-label').textContent=steps[current][0];host.querySelector('.tour-slide-description h3').textContent=steps[current][1];host.querySelector('.tour-slide-description p').textContent=steps[current][2];pointer.classList.toggle('show',current===2);send();}
  function schedule(){clearInterval(timer);host.classList.toggle('tour-running',playing&&visible);if(playing&&visible)timer=setInterval(()=>{current=(current+1)%steps.length;draw()},6500)}
  host.querySelectorAll('[data-tour-step]').forEach(b=>b.onclick=()=>{current=+b.dataset.tourStep;draw();schedule()});
  host.querySelector('.tour-dots').onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();current=e.key==='Home'?0:e.key==='End'?steps.length-1:(current+(e.key==='ArrowRight'?1:steps.length-1))%steps.length;draw();host.querySelectorAll('[data-tour-step]')[current].focus({preventScroll:true});schedule()};
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;schedule()},{threshold:.15}).observe(host);
  frame.onload=send;draw();size();
 });
})();
