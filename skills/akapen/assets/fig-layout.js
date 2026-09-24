/* akapen 図レイアウト: 箱は x,y,幅だけ書く。高さは実測し、被る行を押し下げ、zone は中身に合わせて伸ばし、矢印は箱の縁から引く。
   静的な線 (axis/dot/vline/bars) は <g class="static"> にあり、描き直しの対象外 */
function akLayoutFig(fig){
  var W=+fig.dataset.w||720, GAP=+fig.dataset.gap||16, PAD=10;
  var wrap=fig.querySelector('.fwrap'), cv=fig.querySelector('.fcanvas'), svg=cv.querySelector('.lines');
  if(!wrap||!cv||!svg) return;
  cv.style.transform='none'; cv.style.width=W+'px';
  var all=[].slice.call(cv.querySelectorAll('.node,.note'));
  all.forEach(function(n){n.style.left=n.dataset.x+'px';n.style.top=n.dataset.y+'px';n.style.width=n.dataset.w+'px';n.style.minHeight='';n.classList.remove('pushed');});
  var byParent={};
  all.forEach(function(n){var p=n.dataset.in||'';(byParent[p]=byParent[p]||[]).push(n);});
  var R={};
  function kids(id){return byParent[id]||[];}
  function shiftDesc(id, dy){kids(id).forEach(function(c){c.style.top=(parseFloat(c.style.top)+dy)+'px'; if(R[c.id]){R[c.id].y+=dy;R[c.id].bottom+=dy;} shiftDesc(c.id,dy);});}
  function layoutChildren(parentId){
    var nodes=kids(parentId); if(!nodes.length) return 0;
    nodes.sort(function(a,b){return (+a.dataset.y)-(+b.dataset.y)||(+a.dataset.x)-(+b.dataset.x)});
    var rows=[]; nodes.forEach(function(n){var y=+n.dataset.y, row=rows[rows.length-1]; if(!row||row.y!==y){row={y:y,items:[]};rows.push(row);} row.items.push(n);});
    var placed=[], bottom=0;
    rows.forEach(function(row){
      var top=row.y;
      row.items.forEach(function(n){var x=+n.dataset.x, w=n.offsetWidth;
        placed.forEach(function(p){ if(p.x<x+w && x<p.x+p.w && p.bottom+GAP>top) top=p.bottom+GAP; });});
      row.items.forEach(function(n){
        if(n.classList.contains('zone')){var inner=layoutChildren(n.id); if(inner) n.style.minHeight=(inner+PAD-(+n.dataset.y))+'px';}
        if(top!==row.y) n.classList.add('pushed');
        var dy=top-(+n.dataset.y); n.style.top=top+'px';
        if(dy) shiftDesc(n.id, dy);
        var r={x:+n.dataset.x,y:top,w:n.offsetWidth,h:n.offsetHeight}; r.bottom=r.y+r.h; R[n.id]=r; placed.push(r); if(r.bottom>bottom) bottom=r.bottom;
      });
    });
    return bottom;
  }
  var maxB=layoutChildren('');
  all.forEach(function(n){var r=R[n.id]; if(r){r.y=parseFloat(n.style.top); r.h=n.offsetHeight; r.w=n.offsetWidth; r.bottom=r.y+r.h; if(r.bottom>maxB) maxB=r.bottom;}});
  // 静的な線 (axis 等) の下端も高さに含める
  var st=svg.querySelector('g.static'); if(st){try{var bb=st.getBBox(); if(bb.y+bb.height+8>maxB) maxB=bb.y+bb.height+8;}catch(e){}}
  var H=maxB+12; cv.style.height=H+'px';
  svg.setAttribute('width',W); svg.setAttribute('height',H); svg.setAttribute('viewBox','0 0 '+W+' '+H);
  cv.querySelectorAll('.mark[data-at]').forEach(function(m){var r=R[m.dataset.at]; if(!r) return; m.style.left=(r.x+ +m.dataset.dx)+'px'; m.style.top=(r.y+ +m.dataset.dy)+'px';});
  [].slice.call(svg.querySelectorAll(':scope > path, :scope > text')).forEach(function(e){e.remove();});
  var mk=svg.querySelector('marker[id^=ah-]'), mkr=svg.querySelector('marker[id^=ahr-]');
  function anchor(spec){var p=spec.split(':'), r=R[p[0]], s=p[1]||'r', f=p[2]!==undefined?+p[2]:0.5; if(!r) return null;
    if(s==='l') return {x:r.x, y:r.y+r.h*f, s:s, r:r}; if(s==='r') return {x:r.x+r.w, y:r.y+r.h*f, s:s, r:r};
    if(s==='t') return {x:r.x+r.w*f, y:r.y, s:s, r:r}; return {x:r.x+r.w*f, y:r.y+r.h, s:s, r:r};}
  function hz(s){return s==='l'||s==='r'}
  function normal(a,d){return a.s==='l'?{x:a.x-d,y:a.y}:a.s==='r'?{x:a.x+d,y:a.y}:a.s==='t'?{x:a.x,y:a.y-d}:{x:a.x,y:a.y+d};}
  cv.querySelectorAll('.edge').forEach(function(e){
    var a=anchor(e.dataset.from), b=anchor(e.dataset.to); if(!a||!b) return;
    var d, lx, ly, route=e.dataset.route||'ortho';
    if(route==='straight'){ d='M'+a.x+','+a.y+' L'+b.x+','+b.y; lx=a.x+(b.x-a.x)*0.5; ly=a.y+(b.y-a.y)*0.5-8; }
    else if(route==='curve'){ var dist=Math.hypot(b.x-a.x,b.y-a.y), k=Math.max(30,dist*0.45), c1=normal(a,k), c2=normal(b,k);
      d='M'+a.x+','+a.y+' C'+c1.x+','+c1.y+' '+c2.x+','+c2.y+' '+b.x+','+b.y;
      lx=(a.x+3*c1.x+3*c2.x+b.x)/8; ly=(a.y+3*c1.y+3*c2.y+b.y)/8-6; }
    else if(route==='wrap'){ var my=(a.r.bottom+b.r.y)/2, x1=a.x+6, x2=b.x-6;
      d='M'+a.x+','+a.y+' L'+x1+','+a.y+' L'+x1+','+my+' L'+x2+','+my+' L'+x2+','+b.y+' L'+b.x+','+b.y; lx=(x1+x2)/2; ly=my-5; }
    else if(hz(a.s)&&hz(b.s)){ if(Math.abs(a.y-b.y)<2){d='M'+a.x+','+a.y+' L'+b.x+','+b.y; lx=(a.x+b.x)/2; ly=a.y-6;}
      else {var mx=(a.x+b.x)/2; d='M'+a.x+','+a.y+' L'+mx+','+a.y+' L'+mx+','+b.y+' L'+b.x+','+b.y; lx=mx+4; ly=(a.y+b.y)/2;} }
    else if(!hz(a.s)&&!hz(b.s)){ if(Math.abs(a.x-b.x)<2){d='M'+a.x+','+a.y+' L'+b.x+','+b.y; lx=a.x+6; ly=(a.y+b.y)/2;}
      else {var my2=(a.y+b.y)/2; d='M'+a.x+','+a.y+' L'+a.x+','+my2+' L'+b.x+','+my2+' L'+b.x+','+b.y; lx=(a.x+b.x)/2; ly=my2-5;} }
    else if(hz(a.s)){ d='M'+a.x+','+a.y+' L'+b.x+','+a.y+' L'+b.x+','+b.y; lx=(a.x+b.x)/2; ly=a.y-6; }
    else { d='M'+a.x+','+a.y+' L'+a.x+','+b.y+' L'+b.x+','+b.y; lx=(a.x+b.x)/2; ly=b.y-6; }
    var red=!!e.dataset.red;
    var p=document.createElementNS('http://www.w3.org/2000/svg','path'); p.setAttribute('d',d); p.setAttribute('fill','none');
    p.setAttribute('stroke',red?'#DC2626':'#64707C'); p.setAttribute('stroke-width',red?'1.6':'1.2');
    if(!e.dataset.noarrow){var m=red?mkr:mk; if(m) p.setAttribute('marker-end','url(#'+m.id+')');}
    if(e.dataset.dash) p.setAttribute('stroke-dasharray',red?'5 3':'3 3'); svg.appendChild(p);
    if(e.dataset.label){var t=document.createElementNS('http://www.w3.org/2000/svg','text'); t.setAttribute('x',lx); t.setAttribute('y',ly); t.setAttribute('class','elabel'+(red?' r':'')); t.setAttribute('text-anchor','middle'); t.textContent=e.dataset.label; svg.appendChild(t);}
  });
  // 画面が図より狭ければ縮めて収めるが、文字が読めなくなる手前で打ち止めにする (あふれた分は図だけ横スクロール)。
  // スマホ幅で 720px の図を収めると実効 6px まで落ちて読めないため
  var MINPX=9, base=parseFloat(getComputedStyle(cv).fontSize)||11;
  var s=Math.min(1, (wrap.clientWidth||W)/W);
  if(s*base<MINPX) s=Math.min(1, MINPX/base);
  cv.style.transform='scale('+s+')';
  // transform は要素のレイアウト幅を変えないので、縮小するとその差分だけ余白がスクロールできてしまう。
  // 負の margin でレイアウト幅を縮小後の実寸に合わせる
  cv.style.marginRight = (s<1 ? -(W-W*s) : 0)+'px';
  // 横スクロールが出る環境 (Windows の Chrome 等) では常時表示のスクロールバーが高さを食い、図の下端が欠ける。
  // 実測した差分だけ足す (オーバーレイ表示の macOS・スマホでは 0 になる)
  wrap.style.height=(H*s)+'px';
  var bar=wrap.offsetHeight-wrap.clientHeight;
  if(bar>0) wrap.style.height=(H*s+bar)+'px';
}
function akLayoutAll(){document.querySelectorAll('.fig').forEach(akLayoutFig);}
akLayoutAll(); window.addEventListener('resize',akLayoutAll); if(document.fonts&&document.fonts.ready) document.fonts.ready.then(akLayoutAll);
