// 持续收到事件就延长手势，避免固定节流在惯性尾部再次翻页。
export function createWheelPaging(turn, blocked, now=()=>performance.now()) {
 let last=-Infinity, total=0, fired=false;
 return event=>{
  const time=now();
  if(time-last>280){total=0;fired=false;}
  last=time;
  if(event.ctrlKey||event.metaKey||event.shiftKey||Math.abs(event.deltaX)>=Math.abs(event.deltaY)||!event.deltaY)return;
  if(blocked(event)){fired=true;return;}
  if(!event.cancelable)return;
  event.preventDefault();
  if(fired)return;
  const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?800:1);
  if(Math.sign(delta)!==Math.sign(total))total=0;
  total+=delta;
  if(Math.abs(total)<8)return;
  fired=true;
  turn(Math.sign(total));
 };
}
