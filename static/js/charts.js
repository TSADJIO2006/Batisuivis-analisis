(function () {
  'use strict';
  const data = window.batiChartsData;
  if (!data) return;
  const colors = ['#087cff', '#10d58a', '#8956ff', '#ffad24', '#ff5757', '#22c6d8'];
  const textColor = '#b9cce1', gridColor = '#1d3a56';
  const money = n => new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 0}).format(Number(n) || 0);

  function setup(id) {
    const canvas = document.getElementById(id);
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(260, rect.width || 320), h = 235;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(w * ratio); canvas.height = Math.round(h * ratio);
    canvas.style.width = '100%'; canvas.style.height = h + 'px';
    const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, w, h); ctx.font = '10px Segoe UI, Arial, sans-serif';
    return {ctx, w, h};
  }
  function drawBars(id, labels, values, barColors, suffix='') {
    const o = setup(id); if (!o) return;
    const {ctx, w, h} = o, left=38, right=8, top=12, bottom=43;
    const plotW=w-left-right, plotH=h-top-bottom;
    const nums=values.map(v=>Math.max(0,Number(v)||0));
    const max=Math.max(1,...nums), step=max/4;
    ctx.textAlign='right'; ctx.textBaseline='middle'; ctx.fillStyle=textColor; ctx.strokeStyle=gridColor; ctx.lineWidth=1;
    for(let i=0;i<=4;i++) { const y=top+plotH-(i/4)*plotH; ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.fillText(money(step*i)+suffix,left-6,y); }
    const slot=plotW/Math.max(labels.length,1), bw=Math.min(34,slot*.58);
    nums.forEach((v,i)=>{const bh=(v/max)*plotH,x=left+i*slot+(slot-bw)/2,y=top+plotH-bh;ctx.fillStyle=barColors[i%barColors.length];ctx.beginPath();ctx.roundRect(x,y,bw,Math.max(1,bh),3);ctx.fill();ctx.fillStyle=textColor;ctx.textAlign='center';ctx.textBaseline='top';let label=String(labels[i]??'');if(label.length>13)label=label.slice(5,13)+'…';ctx.fillText(label,x+bw/2,top+plotH+8);});
    if (!nums.some(v=>v>0)) {ctx.fillStyle=textColor;ctx.textAlign='center';ctx.fillText('Aucune donnée à afficher',w/2,h/2);}
  }
  function drawPie(id, labels, values) {
    const o=setup(id); if(!o)return; const {ctx,w,h}=o;
    const nums=values.map(v=>Math.max(0,Number(v)||0)), total=nums.reduce((a,b)=>a+b,0);
    const cx=Math.min(w*.34,105),cy=94,r=Math.min(66,w*.23); let angle=-Math.PI/2;
    if(total>0){nums.forEach((v,i)=>{const next=angle+(v/total)*Math.PI*2;ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,r,angle,next);ctx.closePath();ctx.fillStyle=colors[i%colors.length];ctx.fill();angle=next;});ctx.beginPath();ctx.arc(cx,cy,r*.57,0,Math.PI*2);ctx.fillStyle='#0a2137';ctx.fill();ctx.fillStyle='#f2f7ff';ctx.textAlign='center';ctx.textBaseline='middle';ctx.font='bold 12px Segoe UI,Arial';ctx.fillText(money(total),cx,cy);}
    else {ctx.fillStyle=textColor;ctx.textAlign='center';ctx.fillText('Aucune dépense',cx,cy);}
    ctx.font='10px Segoe UI,Arial';ctx.textBaseline='middle';
    const lx=Math.min(w*.62,190); let ly=36;
    labels.slice(0,6).forEach((label,i)=>{ctx.fillStyle=colors[i%colors.length];ctx.fillRect(lx,ly-5,8,8);ctx.fillStyle=textColor;ctx.textAlign='left';let name=String(label);if(name.length>15)name=name.slice(0,14)+'…';ctx.fillText(name,lx+13,ly);ctx.textAlign='right';ctx.fillText(money(nums[i]||0),w-6,ly);ly+=25;});
  }
  function render(){drawBars('pChart',data.dates||[],data.daily||[],[colors[0]]);drawPie('eChart',data.categories||[],data.expenses||[]);drawBars('cChart',data.activityLabels||[],data.activityRates||[],[colors[1]],'%');drawBars('phaseCostChart',data.phaseCostLabels||[],data.phaseCosts||[],[colors[2]],' FCFA');}
  render(); let resizeTimer; window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(render,120);});
})();
