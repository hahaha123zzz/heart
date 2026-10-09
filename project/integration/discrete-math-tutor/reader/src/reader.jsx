import React, {useState,useRef,useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {PdfLoader,PdfHighlighter,Highlight,AreaHighlight} from 'react-pdf-highlighter';
import './reader.css';
import renderMathInElement from 'katex/contrib/auto-render';
import 'katex/dist/katex.min.css';
class ReaderHighlighter extends PdfHighlighter {
 componentWillUnmount(){
  super.componentWillUnmount();
  this.debouncedScaleValue?.clear?.();
  this.debouncedAfterSelection?.clear?.();
  // 组件卸载后终止 PDF.js 页面任务，避免隐藏页仍触发定位。
  this.viewer?.setDocument(null);
 }
}
const mounted=new Map();
const clamp=x=>Math.max(0,Math.min(1,x));
function normalized(position,kind){
 const rectangles=kind==='area'?[position.boundingRect]:(position.rects.length?position.rects:[position.boundingRect]);
 return rectangles.map(r=>({page:r.pageNumber||position.pageNumber,x1:clamp(r.x1/r.width),y1:clamp(r.y1/r.height),x2:clamp(r.x2/r.width),y2:clamp(r.y2/r.height)}));
}
function asHighlight(ref){
 const rects=ref.rects.map(r=>({x1:r.x1,y1:r.y1,x2:r.x2,y2:r.y2,width:1,height:1,pageNumber:r.page}));
 const first=rects.filter(r=>r.pageNumber===rects[0].pageNumber);
 return {id:'selection',content:{text:ref.text||''},comment:{text:'',emoji:''},position:{pageNumber:rects[0].pageNumber,
 boundingRect:{...first[0],x1:Math.min(...first.map(r=>r.x1)),y1:Math.min(...first.map(r=>r.y1)),x2:Math.max(...first.map(r=>r.x2)),y2:Math.max(...first.map(r=>r.y2))},rects}};
}
function Reader({metadata,reference,onAsk}){
 const [mode,setMode]=useState('text'),[scale,setScale]=useState('page-width'),[page,setPage]=useState(metadata.section.page),[tip,setTip]=useState(null),[error,setError]=useState('');
 const modeRef=useRef(mode);modeRef.current=mode;
 const highlighter=useRef(null),scrollTo=useRef(null),drag=useRef(null),surface=useRef(null);
 const [touchBox,setTouchBox]=useState(null);
 const [ready,setReady]=useState(false);
 const sourcePage=n=>metadata.page_map?.[n-1] || n;
 const displayPage=n=>metadata.page_map ? metadata.page_map.indexOf(n)+1 : n;
 const mappedReference=reference ? {...reference,rects:reference.rects.map(rect=>({...rect,page:displayPage(rect.page)})).filter(rect=>rect.page>0)} : null;
 const highlights=mappedReference?.rects.length&&reference.document_id===metadata.document_id&&reference.version===metadata.version?[asHighlight(mappedReference)]:[];
 function jump(target,y=0){
   if(!scrollTo.current||!surface.current?.offsetParent)return;
   scrollTo.current({id:'jump',position:{pageNumber:target,boundingRect:{x1:0,y1:y,x2:.01,y2:y+.002,width:1,height:1},rects:[]},content:{},comment:{text:'',emoji:''}});
 }
 // PDF pagesinit 之后再消费最新导航目标；渲染完成前的请求不会被丢弃。
 useEffect(()=>{
  if(!ready)return;
  const frame=requestAnimationFrame(()=>{
   if(!scrollTo.current||!surface.current?.offsetParent)return;
   if(highlights.length)scrollTo.current(highlights[0]);else jump(metadata.section.page,metadata.section.y);
  });
  return()=>cancelAnimationFrame(frame);
 },[ready,metadata.section.id,metadata.section.page,metadata.section.y,reference]);
 useEffect(()=>{
  if(!ready)return;
  const viewer=highlighter.current?.viewer;
  if(!viewer)return;
  const changed=e=>setPage(e.pageNumber);
  viewer.eventBus.on('pagechanging',changed);
  setPage(viewer.currentPageNumber);
  return()=>viewer.eventBus.off('pagechanging',changed);
 },[ready]);
 useEffect(()=>{const close=e=>{if(e.key==='Escape'){setTip(null);setTouchBox(null);highlighter.current?.hideTipAndSelection();}}; document.addEventListener('keydown',close);return()=>document.removeEventListener('keydown',close);},[]);
 function makeSelection(position,content,hide){
  if(!onAsk)return null;
  const kind=content.image?'area':'text';
  const selection={document_id:metadata.document_id,version:metadata.version,kind,rects:normalized(position,kind).map(rect=>({...rect,page:sourcePage(rect.page)})),text:(content.text||'').slice(0,4000)};
  return <div className="pdf-selection-menu" onPointerDown={e=>e.stopPropagation()}>
   <button type="button" onClick={()=>{onAsk(selection);hide();window.getSelection()?.removeAllRanges();setTip(null);}}>向 AI 提问</button>
   <button type="button" onClick={()=>{hide();setTip(null);window.getSelection()?.removeAllRanges();}}>取消</button>
  </div>;
 }
 function changeScale(value){setScale(value);if(highlighter.current?.viewer) highlighter.current.viewer.currentScaleValue=value;}
 function pointerDown(e){
  if(!onAsk||mode!=='area'||e.pointerType!=='touch')return;
  const element=e.target.closest('.page');if(!element)return;
  e.preventDefault();e.stopPropagation();const box=element.getBoundingClientRect();
  drag.current={box,page:Number(element.dataset.pageNumber),x:e.clientX,y:e.clientY};
  e.currentTarget.setPointerCapture(e.pointerId);setTip(null);
 }
 function pointerMove(e){if(!drag.current)return;e.preventDefault();const d=drag.current;const b=surface.current.getBoundingClientRect();setTouchBox({left:Math.min(d.x,e.clientX)-b.left,top:Math.min(d.y,e.clientY)-b.top,width:Math.abs(d.x-e.clientX),height:Math.abs(d.y-e.clientY)});}
 function pointerUp(e){
  if(!drag.current)return;e.preventDefault();const d=drag.current;drag.current=null;setTouchBox(null);
  const r={page:d.page,x1:clamp((Math.min(d.x,e.clientX)-d.box.left)/d.box.width),y1:clamp((Math.min(d.y,e.clientY)-d.box.top)/d.box.height),x2:clamp((Math.max(d.x,e.clientX)-d.box.left)/d.box.width),y2:clamp((Math.max(d.y,e.clientY)-d.box.top)/d.box.height)};
  if((r.x2-r.x1)*d.box.width<5||(r.y2-r.y1)*d.box.height<5)return;
  setTip({document_id:metadata.document_id,version:metadata.version,kind:'area',rects:[{...r,page:sourcePage(r.page)}],text:''});
 }
 return <div className="pdf-reader" data-document={metadata.document_id}>
  <div className="pdf-toolbar">
   <button type="button" onClick={()=>jump(Math.max(1,page-1))} aria-label="上一页">‹</button>
   <label>页 <input aria-label="PDF 页码" type="number" min="1" max={metadata.page_count} value={page} onChange={e=>{const n=Number(e.target.value);if(n>=1&&n<=metadata.page_count)jump(n);}}/> / {metadata.page_count}</label>
   {metadata.page_map&&<span className="pdf-source-page">原教材第 {sourcePage(page)} 页</span>}
   <button type="button" onClick={()=>jump(Math.min(metadata.page_count,page+1))} aria-label="下一页">›</button>
   <select aria-label="PDF 缩放" value={scale} onChange={e=>changeScale(e.target.value)}><option value="page-width">适合宽度</option><option value="1">100%</option><option value="1.25">125%</option><option value="1.5">150%</option><option value="2">200%</option></select>
   {onAsk&&<button type="button" aria-pressed={mode==='area'} className={mode==='area'?'active':''} onClick={()=>{setMode(mode==='area'?'text':'area');highlighter.current?.hideTipAndSelection();setTip(null);}}>{mode==='area'?'退出框选':'框选图 / 公式'}</button>}
  </div>
  <div className="pdf-hint" role="status">{error|| (!onAsk?'根据题目独立作答，可使用页码或练习分组切换。':mode==='area'?'拖动框选一页内的图、公式或表格，然后向 AI 提问。':'划选文字向 AI 提问；图和公式可使用框选。')}</div>
  <div className={'pdf-surface '+(mode==='area'?'area-mode':'')} ref={surface} onPointerDownCapture={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={()=>{drag.current=null;setTouchBox(null);}}>
   <PdfLoader key={metadata.document_id} url={metadata.url} workerSrc="/static/pdf-reader/pdf.worker.min.mjs" cMapUrl="/static/pdf-reader/cmaps/" cMapPacked standardFontDataUrl="/static/pdf-reader/standard_fonts/" isEvalSupported={false}
    beforeLoad={<div className="pdf-loading">正在加载原版教材…</div>} onError={()=>setError('PDF 加载失败，请刷新重试')} errorMessage={<div className="pdf-loading">PDF 加载失败，请刷新重试。</div>}>
    {document=><ReaderHighlighter ref={highlighter} pdfDocument={document} pdfScaleValue={scale} highlights={highlights}
     enableAreaSelection={e=>Boolean(onAsk)&&modeRef.current==='area'&&e.button===0} onSelectionFinished={makeSelection} onScrollChange={()=>{}}
     scrollRef={fn=>{scrollTo.current=fn;setReady(true);}}
     highlightTransform={(highlight,index,setTip,hideTip,viewportToScaled,screenshot,isScrolledTo)=>reference?.kind==='area'?<AreaHighlight key={index} highlight={highlight} onChange={()=>{}}/>:<Highlight key={index} position={highlight.position} comment={highlight.comment} isScrolledTo={isScrolledTo}/>}/>} 
   </PdfLoader>
   {touchBox&&<div className="pdf-touch-selection" style={touchBox}/>}
   {tip&&<div className="pdf-touch-menu"><button type="button" onClick={()=>{onAsk(tip);setTip(null);}}>向 AI 提问</button><button type="button" onClick={()=>setTip(null)}>取消</button></div>}
  </div>
 </div>;
}
window.TextbookPDF={
renderMath(element){renderMathInElement(element,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false},{left:'\\(',right:'\\)',display:false},{left:'\\[',right:'\\]',display:true}],throwOnError:false,trust:false,strict:'ignore'});},
mount(element,metadata,reference,onAsk){let instance=mounted.get(element);if(!instance){instance=createRoot(element);mounted.set(element,instance);}instance.render(<Reader key={metadata.document_id} metadata={metadata} reference={reference} onAsk={onAsk}/>);},
unmount(element){const instance=mounted.get(element);if(instance){instance.unmount();mounted.delete(element);}}
};
window.dispatchEvent(new Event('pdf-reader-ready'));
