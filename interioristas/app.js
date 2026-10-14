const track = document.querySelector('.projects .three-grid');
if (track) {
  const originals = [...track.children];
  const viewport = document.createElement('div');
  viewport.className = 'projects-viewport';
  viewport.setAttribute('aria-label', 'Proyectos: arrastra para explorar');
  track.before(viewport); viewport.append(track);
  for (const side of ['before', 'after']) {
    const copies = originals.map(card => { const copy = card.cloneNode(true); copy.tabIndex = -1; copy.setAttribute('aria-hidden','true'); return copy; });
    if (side === 'before') track.prepend(...copies); else track.append(...copies);
  }
  const controls = document.createElement('div');
  controls.className = 'projects-controls';
  controls.innerHTML = '<span>Arrastra para explorar</span><button type="button" aria-label="Proyecto anterior">←</button><button type="button" aria-label="Proyecto siguiente">→</button><button type="button" class="project-pause"></button>';
  viewport.after(controls);
  const pause = controls.querySelector('.project-pause');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reduced.matches, hovering = false, dragging = false, startX = 0, startScroll = 0, moved = false;
  const step = () => originals[0].getBoundingClientRect().width + parseFloat(getComputedStyle(track).gap);
  const span = () => step() * originals.length;
  const label = () => { pause.textContent = paused ? 'Reanudar →' : 'Pausar Ⅱ'; pause.setAttribute('aria-label',paused?'Reanudar proyectos':'Pausar proyectos'); };
  const stop = () => { paused=true; label(); };
  label();
  requestAnimationFrame(()=>viewport.scrollLeft=span());
  new ResizeObserver(()=>{if(!dragging) viewport.scrollLeft=span();}).observe(viewport);
  viewport.addEventListener('scroll',()=>{
    if(dragging) return;
    const size=span();
    if(viewport.scrollLeft < size*.25) viewport.scrollLeft+=size;
    else if(viewport.scrollLeft > size*1.75) viewport.scrollLeft-=size;
  });
  function advance(direction) { viewport.scrollBy({left:step()*direction,behavior:reduced.matches?'instant':'smooth'}); }
  controls.querySelector('[aria-label="Proyecto anterior"]').onclick=()=>{stop();advance(-1);};
  controls.querySelector('[aria-label="Proyecto siguiente"]').onclick=()=>{stop();advance(1);};
  pause.onclick=()=>{paused=!paused;label();};
  viewport.addEventListener('mouseenter',()=>hovering=true);
  viewport.addEventListener('mouseleave',()=>hovering=false);
  viewport.addEventListener('dragstart',e=>e.preventDefault());
  viewport.addEventListener('pointerdown',e=>{
    stop(); moved=false;
    if(e.pointerType==='touch'||e.button!==0) return;
    dragging=true;startX=e.clientX;startScroll=viewport.scrollLeft;
  });
  window.addEventListener('pointermove',e=>{
    if(!dragging)return;
    const delta=e.clientX-startX;
    if(Math.abs(delta)>5){moved=true;viewport.classList.add('dragging');viewport.setPointerCapture(e.pointerId);}
    viewport.scrollLeft=startScroll-delta;
  });
  const release=()=>{dragging=false;viewport.classList.remove('dragging');};
  window.addEventListener('pointerup',release);window.addEventListener('pointercancel',release);
  viewport.addEventListener('click',e=>{if(moved){e.preventDefault();e.stopPropagation();moved=false;}},true);
  setInterval(()=>{
    const bounds=viewport.getBoundingClientRect();
    if(!paused&&!hovering&&!dragging&&!document.hidden&&!viewport.contains(document.activeElement)&&bounds.bottom>0&&bounds.top<innerHeight) advance(1);
  },6000);
}
