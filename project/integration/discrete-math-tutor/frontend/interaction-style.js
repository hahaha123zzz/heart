"use strict";

// 临时偏好只属于当前学生、当前标签的会话；确认前不改变任何参数。
class InteractionStyle {
  constructor(storage, key) {
    this.storage=storage;this.key=key;
    try { this.data=JSON.parse(storage.getItem(key)) || {}; } catch { this.data={}; }
    this.data={session:{},once:null,turns:0,nextOffer:0,seen:[],...this.data};
  }
  save() { this.storage.setItem(this.key,JSON.stringify(this.data)); }
  snapshot() { return {values:{...this.data.session,...this.data.once?.values},onceId:this.data.once?.id}; }
  apply(values,scope,id) {
    if(scope==='next')this.data.once={id,values};
    else if(scope==='session')Object.assign(this.data.session,values);
    if(scope==='session' || scope==='long'){
      for(const key of Object.keys(values)){
        if(scope==='long')delete this.data.session[key];
        if(this.data.once)delete this.data.once.values[key];
      }
      if(this.data.once && !Object.keys(this.data.once.values).length)this.data.once=null;
    }
    this.dismiss();
  }
  consume(onceId) {
    if(onceId && this.data.once?.id===onceId){this.data.once=null;this.save();}
  }
  clear() { this.data.session={};this.data.once=null;this.save(); }
  dismiss() { this.data.nextOffer=this.data.turns+6;this.save(); }
  observe(result) {
    if(result.answer_status!=='answered' || !result.task_id || this.data.seen.includes(result.task_id))return null;
    this.data.seen.push(result.task_id);this.data.seen=this.data.seen.slice(-32);this.data.turns++;
    const offer=this.data.turns>=this.data.nextOffer?result.style_suggestion:null;
    if(offer)this.data.nextOffer=this.data.turns+6;
    this.save();return offer;
  }
}
if(typeof window!=='undefined')window.InteractionStyle=InteractionStyle;
if(typeof module!=='undefined')module.exports=InteractionStyle;
