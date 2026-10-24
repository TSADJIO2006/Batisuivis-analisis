(()=>{
'use strict';
const source=window.batiAnalysisData;if(!source)return;
const palette=['#087cff','#10d58a','#ffad24','#8956ff','#ff5757','#22c6d8','#f472b6'];
const fmt=n=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1}).format(Number(n)||0);
const money=n=>new Intl.NumberFormat('fr-FR',{maximumFractionDigits:0}).format(Number(n)||0)+' FCFA';
const $=id=>document.getElementById(id);
function canvas(id){const el=$(id);if(!el)return null;const w=Math.max(280,el.clientWidth||320),h=270,dpr=window.devicePixelRatio||1;el.width=w*dpr;el.height=h*dpr;el.style.height=h+'px';const c=el.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,w,h);c.font='11px Segoe UI,Arial';return {el,c,w,h};}
function frame(o,max){const {c,w,h}=o,L=48,R=14,T=15,B=44,pw=w-L-R,ph=h-T-B; c.strokeStyle='#1d3a56';c.fillStyle='#b9cce1';c.lineWidth=1;for(let i=0;i<=4;i++){let y=T+ph-i*ph/4;c.beginPath();c.moveTo(L,y);c.lineTo(w-R,y);c.stroke();c.textAlign='right';c.textBaseline='middle';c.fillText(fmt(max*i/4),L-7,y);}return {L,R,T,B,pw,ph};}
function lineChart(id,labels,series){const o=canvas(id);if(!o)return;const {c,w,h}=o;if(!labels.length){c.fillStyle='#b9cce1';c.textAlign='center';c.fillText('Aucune donnée pour cette période',w/2,h/2);return;}const max=Math.max(1,...series.flatMap(s=>s.values.map(v=>Math.abs(v))));const f=frame(o,max);series.forEach(s=>{c.strokeStyle=s.color;c.lineWidth=2.5;c.beginPath();s.values.forEach((v,i)=>{const x=f.L+(labels.length===1?f.pw/2:i*f.pw/(labels.length-1)),y=f.T+f.ph/2-(v/max)*f.ph/2; i?c.lineTo(x,y):c.moveTo(x,y);});c.stroke();s.values.forEach((v,i)=>{const x=f.L+(labels.length===1?f.pw/2:i*f.pw/(labels.length-1)),y=f.T+f.ph/2-(v/max)*f.ph/2;c.fillStyle=s.color;c.beginPath();c.arc(x,y,3,0,Math.PI*2);c.fill();});});c.fillStyle='#b9cce1';c.textAlign='center';c.textBaseline='top';const every=Math.max(1,Math.ceil(labels.length/7));labels.forEach((v,i)=>{if(i%every===0||i===labels.length-1)c.fillText(v.slice(5),f.L+(labels.length===1?f.pw/2:i*f.pw/(labels.length-1)),f.T+f.ph+9);});}
function bars(id,labels,series){const o=canvas(id);if(!o)return;const {c,w,h}=o;if(!labels.length){c.fillStyle='#b9cce1';c.textAlign='center';c.fillText('Aucune donnée à afficher',w/2,h/2);return;}const max=Math.max(1,...series.flatMap(s=>s.values.map(v=>Math.abs(v))));const f=frame(o,max),slot=f.pw/labels.length,bw=Math.min(25,slot/(series.length+1));labels.forEach((lab,i)=>{series.forEach((s,j)=>{const v=s.values[i]||0,bh=Math.abs(v)/max*f.ph,x=f.L+i*slot+slot/2+(j-(series.length-1)/2)*bw-bw/2,y=v>=0?f.T+f.ph-bh:f.T+f.ph/2;c.fillStyle=s.color;c.fillRect(x,y,bw,Math.max(1,bh));});c.fillStyle='#b9cce1';c.textAlign='center';c.textBaseline='top';let txt=lab.length>12?lab.slice(0,11)+'…':lab;c.fillText(txt,f.L+i*slot+slot/2,f.T+f.ph+8);});}
function donut(id,items){const o=canvas(id);if(!o)return;const {c,w,h}=o;const total=items.reduce((a,x)=>a+x.amount,0);if(!total){c.fillStyle='#b9cce1';c.textAlign='center';c.fillText('Aucune dépense enregistrée',w/2,h/2);return;}const cx=w*.32,cy=h*.48,r=Math.min(78,w*.22);let a=-Math.PI/2;items.forEach((it,i)=>{const b=a+it.amount/total*Math.PI*2;c.beginPath();c.moveTo(cx,cy);c.arc(cx,cy,r,a,b);c.closePath();c.fillStyle=palette[i%palette.length];c.fill();a=b;});c.beginPath();c.arc(cx,cy,r*.58,0,Math.PI*2);c.fillStyle='#0a2137';c.fill();c.fillStyle='#f2f7ff';c.textAlign='center';c.textBaseline='middle';c.font='bold 12px Segoe UI';c.fillText(money(total).replace(' FCFA',''),cx,cy);c.font='11px Segoe UI';items.slice(0,7).forEach((it,i)=>{let y=34+i*29,x=w*.58;c.fillStyle=palette[i%palette.length];c.fillRect(x,y-5,9,9);c.fillStyle='#b9cce1';c.textAlign='left';c.fillText(it.category.length>15?it.category.slice(0,14)+'…':it.category,x+14,y);c.textAlign='right';c.fillText(money(it.amount),w-8,y);});}
function render(){
 const from=$('analysisFrom').value,to=$('analysisTo').value;
 const rows=source.progress.filter(r=>(!from||r.date>=from)&&(!to||r.date<=to));
 const summary=$('analysisSummary'), conclusions=$('analysisConclusions');
 if(source.mode==='global'){
  const sites=[...new Set(rows.map(r=>r.site))];
  const dates=[...new Set(rows.map(r=>r.date))].sort();
  const perSite={};sites.forEach(s=>perSite[s]={planned:0,actual:0,byDate:{}});
  rows.forEach(r=>{const o=perSite[r.site];o.planned+=r.planned;o.actual+=r.actual;if(!o.byDate[r.date])o.byDate[r.date]={planned:0,actual:0};o.byDate[r.date].planned+=r.planned;o.byDate[r.date].actual+=r.actual;});
  const series=sites.map((site,i)=>{let p=0,a=0;return {name:site,color:palette[i%palette.length],values:dates.map(d=>{const v=perSite[site].byDate[d];if(v){p+=v.planned;a+=v.actual;}return p?a/p*100:0;})};});
  lineChart('analysisProgressChart',dates,series);
  const deviations=sites.map((site,i)=>({name:site,color:palette[i%palette.length],values:[perSite[site].planned?(perSite[site].actual/perSite[site].planned*100)-100:0]}));
  bars('analysisDeviationChart',sites,deviations);
  const comp=source.siteComparison||[];
  bars('analysisActivityChart',comp.map(x=>x.name),[{name:'Taux réalisé',values:comp.map(x=>x.rate),color:palette[1]}]);
  donut('analysisCostsChart',comp.map(x=>({category:x.name,amount:Number(x.expenses||0)})).filter(x=>x.amount>0));
  const lowest=[...comp].sort((a,b)=>a.rate-b.rate)[0],highest=[...comp].sort((a,b)=>b.rate-a.rate)[0],over=comp.filter(x=>x.expenses>x.budget).length;
  const planned=rows.reduce((a,r)=>a+r.planned,0),actual=rows.reduce((a,r)=>a+r.actual,0);
  summary.textContent=`Vue globale : ${sites.length} chantier(s) et ${rows.length} relevé(s) dans la période. Les courbes d’avancement sont exprimées en pourcentage cumulé par chantier pour ne pas additionner les unités physiques différentes.`;
  const notes=[];
  if(highest)notes.push(`Meilleur taux de réalisation cumulé : ${highest.name} (${fmt(highest.rate)} %).`);
  if(lowest)notes.push(`Taux le plus faible : ${lowest.name} (${fmt(lowest.rate)} %). Il faut examiner ses activités en retard et ses contraintes d’approvisionnement.`);
  if(over)notes.push(`${over} chantier(s) présentent des dépenses supérieures au budget enregistré : vérifier les montants, le budget initial et les engagements à venir.`);
  if(comp.length&&comp.every(x=>x.expenses<=x.budget))notes.push('Aucun dépassement du budget enregistré n’apparaît dans les données actuelles ; cela ne garantit pas que les dépenses futures resteront dans l’enveloppe.');
  if(planned>0&&actual<planned)notes.push('Sur les relevés filtrés, la quantité réalisée est inférieure à la quantité prévue. Examiner les écarts chantier par chantier avant de réviser les délais.');
  conclusions.innerHTML='<strong>Conclusions automatiques</strong><ul>'+notes.map(n=>'<li>'+n.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')+'</li>').join('')+'</ul>';
 }else{
  const daily={};rows.forEach(r=>{if(!daily[r.date])daily[r.date]={planned:0,actual:0};daily[r.date].planned+=r.planned;daily[r.date].actual+=r.actual;});const dates=Object.keys(daily).sort();
  lineChart('analysisProgressChart',dates,[{name:'Prévu',values:dates.map(d=>daily[d].planned),color:palette[0]},{name:'Réalisé',values:dates.map(d=>daily[d].actual),color:palette[1]}]);
  lineChart('analysisDeviationChart',dates,[{name:'Écart',values:dates.map(d=>daily[d].actual-daily[d].planned),color:palette[2]}]);
  const acts={};rows.forEach(r=>{const key=r.activity+' ('+r.unit+')';if(!acts[key])acts[key]={planned:0,actual:0};acts[key].planned+=r.planned;acts[key].actual+=r.actual;});const names=Object.keys(acts);
  bars('analysisActivityChart',names,[{name:'Prévu',values:names.map(n=>acts[n].planned),color:palette[0]},{name:'Réalisé',values:names.map(n=>acts[n].actual),color:palette[1]}]);donut('analysisCostsChart',(source.costs||[]).map(x=>({category:String(x.category||'Autre'),amount:Number(x.total??x.amount??0)})).filter(x=>x.amount>0));
  const planned=rows.reduce((a,r)=>a+r.planned,0),actual=rows.reduce((a,r)=>a+r.actual,0),hours=rows.reduce((a,r)=>a+r.hours,0),rate=planned?actual/planned*100:0,expense=source.costs.reduce((a,c)=>a+c.amount,0);
  summary.textContent=`${source.siteName} — ${rows.length} relevé(s) sur la période. Prévu : ${fmt(planned)} ; réalisé : ${fmt(actual)} ; écart : ${fmt(actual-planned)} ; productivité brute : ${fmt(hours?actual/hours:0)} quantité(s)/heure. Les dépenses correspondent à l’ensemble du chantier et ne sont pas filtrées par date.`;
  const notes=[];if(planned&&actual<planned)notes.push(`Le taux de réalisation sur la période est de ${fmt(rate)} % : le chantier est en retard par rapport aux quantités prévues sur les relevés filtrés.`);else if(planned)notes.push(`Le taux de réalisation sur la période est de ${fmt(rate)} % : les quantités réalisées atteignent ou dépassent le cumul prévu.`);
  const behind=Object.entries(acts).map(([name,v])=>({name,rate:v.planned?v.actual/v.planned*100:0})).filter(x=>x.rate<90).sort((a,b)=>a.rate-b.rate);
  if(behind.length)notes.push(`Activité(s) à surveiller (moins de 90 % du prévu) : ${behind.slice(0,3).map(x=>x.name+' ('+fmt(x.rate)+' %)').join(', ')}.`);
  if(source.budget&&expense/source.budget>0.8)notes.push(`Les dépenses enregistrées représentent ${fmt(expense/source.budget*100)} % du budget. Comparer cette consommation à l’avancement physique et aux travaux restant à réaliser.`);
  if(!rows.length)notes.push('Aucun relevé dans cette période : élargis les dates ou ajoute des données dans Collecte de données.');
  conclusions.innerHTML='<strong>Conclusions automatiques</strong><ul>'+notes.map(n=>'<li>'+n.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')+'</li>').join('')+'</ul>';
 }
}
$('analysisFrom').addEventListener('change',render);$('analysisTo').addEventListener('change',render);$('analysisReset').addEventListener('click',()=>{$('analysisFrom').value='';$('analysisTo').value='';render();});let timer;window.addEventListener('resize',()=>{clearTimeout(timer);timer=setTimeout(render,150);});render();
})();