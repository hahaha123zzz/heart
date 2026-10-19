"use strict";

window.PsychologyFigures={
 render(host,frame){
  host.replaceChildren();host.hidden=!frame.signal&&!frame.spatial;
  if(host.hidden)return;
  const node=(tag,text,className)=>{const el=document.createElement(tag);if(text!=null)el.textContent=text;if(className)el.className=className;return el;};
  const svgNode=(tag,attrs={})=>{const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs))el.setAttribute(key,String(value));return el;};
  const plot=(box,label)=>{const svg=svgNode('svg',{viewBox:box,role:'img','aria-label':label});const title=svgNode('title');title.textContent=label;svg.append(title);return svg;};
  const path=(svg,d,color,fill='none',dash='')=>{const p=svgNode('path',{d,stroke:color,fill,'fill-opacity':fill==='none'?1:.55,'stroke-width':2.5});if(dash)p.setAttribute('stroke-dasharray',dash);svg.append(p);};
  const label=(svg,x,y,text)=>{const t=svgNode('text',{x,y,'font-size':17,fill:'#344b5a','text-anchor':'middle'});t.style.stroke='none';t.textContent=text;svg.append(t);};
  if(frame.signal){
   const s=frame.signal;host.dataset.phase=String(s.phase);
   host.append(node('p',`等方差正态模型 · d′ = ${s.d_prime} · 教学示意，非实测数据`,'psychology-model'));
   const density=plot('0 0 520 210','噪声与信号加噪声的内部反应分布；横轴内部反应强度，纵轴概率密度');
   path(density,'M42,164 L492,164','#6d808d');
   if(s.phase>=1){path(density,s.noise_area,'none','#c8dcf0');path(density,s.signal_area,'none','#b9dfd0');}
   if(s.previous_signal_path)path(density,s.previous_signal_path,'#788691','none','6 5');
   path(density,s.noise_path,'#285c91');path(density,s.signal_path,'#226a50');
   for(const value of [-2,0,2,4])label(density,42+(value+3.5)/9*450,187,String(value));
   if(s.phase>=1){path(density,`M${s.criterion_x},26 L${s.criterion_x},164`,'#9a4d20','none','5 4');label(density,s.criterion_x,20,'判准');}
   host.append(density,node('p','横轴：内部反应强度（示意标准单位） · 纵轴：概率密度','psychology-axis'));
   const legend=node('p',null,'psychology-legend');
   for(const [text,color] of [['噪声','#285c91'],['信号＋噪声','#226a50']]){const key=node('span',text);key.style.setProperty('--curve-color',color);legend.append(key);}host.append(legend);
   if(s.phase>=1)host.append(node('p',`判准右侧回答“有信号”；当前位置 x = ${s.criterion}。阴影是两种实际状态各自的右尾。`,'psychology-caption'));
   if(s.phase>=2){
    const table=node('table',null,'signal-outcomes'),caption=node('caption','判断结果（每种实际状态下的条件概率）');table.append(caption);
    const header=node('tr');for(const text of ['实际状态','回答有信号','回答无信号']){const th=node('th',text);th.scope='col';header.append(th);}const head=node('thead');head.append(header);table.append(head);
    const body=node('tbody');
    for(const [name,yes,no] of [['有信号',['击中',s.rates.hit],['漏报',s.rates.miss]],['无信号',['虚报',s.rates.false_alarm],['正确否定',s.rates.correct_rejection]]]){
     const row=node('tr'),th=node('th',name);th.scope='row';row.append(th);for(const [name,rate] of [yes,no])row.append(node('td',`${name} ${(rate*100).toFixed(1)}%`));body.append(row);
    }table.append(body);host.append(table);
   }
   if(s.phase>=4){
    const roc=plot('0 0 390 260','概率坐标ROC：横轴虚报率，纵轴击中率；圆点与当前判准来自同一正态模型');
    path(roc,'M48,28 L48,218 L338,218','#6d808d');
    if(s.previous_roc_path)path(roc,s.previous_roc_path,'#788691','none','6 5');path(roc,s.roc_path,'#226a50');
    const points=s.previous_point?[s.previous_point,s.roc_points[1]]:s.roc_points;
    points.forEach((p,i)=>{roc.append(svgNode('circle',{cx:p.x,cy:p.y,r:i?6:5,fill:i?'#9a4d20':'#285c91','data-roc-point':i}));});
    for(const value of [0,.5,1]){label(roc,48+value*290,242,String(value));label(roc,26,223-value*190,String(value));}
    roc.classList.add('psychology-roc');host.append(roc,node('p','横轴：虚报率 · 纵轴：击中率（概率坐标，非 zROC）','psychology-axis'),node('p',s.previous_point?'蓝点：原条件；棕点：当前条件。虚线：原ROC。':'蓝点：较宽松判准；棕点：当前较严格判准。','psychology-caption'));
   }
  }
  if(frame.spatial){
   const phase=frame.spatial.phase;host.dataset.phase=phase;
   const timeline=node('ol',null,'spatial-timeline');for(const [i,text] of ['注视点','外围线索','目标'].entries()){const step=node('li',text);if(i===(phase==='fixation'?0:phase==='cue'?1:2)){step.className='active';step.setAttribute('aria-current','step');}timeline.append(step);}host.append(timeline);
   const trial=(state,title)=>{
    const figure=node('figure',null,'spatial-trial');figure.append(node('figcaption',title));
    const svg=plot('0 0 480 180',title+'；中央注视点，线索在左侧，目标'+(state==='invalid'?'在右侧':state==='valid'?'在左侧':'尚未出现'));
    path(svg,'M230,95 L250,95 M240,85 L240,105','#344b5a');
    for(const [x,side] of [[50,'左侧位置'],[330,'右侧位置']]){svg.append(svgNode('rect',{x,y:60,width:100,height:70,rx:5,fill:'#f6f8fa',stroke:'#8a9eab','stroke-width':2}));label(svg,x+50,40,side);}
    if(state!=='fixation'){const outline=svgNode('rect',{x:50,y:60,width:100,height:70,rx:5,fill:'none',stroke:'#9a4d20','stroke-width':4});if(state!=='cue')outline.setAttribute('stroke-dasharray','7 5');svg.append(outline);label(svg,100,160,state==='cue'?'线索':'先前线索位置');}
    if(state==='valid'||state==='invalid'){const x=state==='valid'?100:380;svg.append(svgNode('circle',{cx:x,cy:95,r:13,fill:'#285c91','data-target-position':state==='valid'?'left':'right'}));label(svg,x,120,'目标');}
    figure.append(svg);return figure;
   };
   if(phase==='compare'){host.append(trial('valid','有效条件：目标与先前线索同侧'),trial('invalid','无效条件：目标与先前线索异侧'));}
   else host.append(trial(phase,phase==='invalid'?'另一试次：无效条件':phase==='valid'?'有效条件':phase==='cue'?'外围线索呈现':'注视点呈现'));
   host.append(node('p','翻步为机制演示，不表示真实毫秒时序；未收集个人反应时。','psychology-caption'));
  }
 }
};
