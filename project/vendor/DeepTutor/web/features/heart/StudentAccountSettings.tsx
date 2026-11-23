"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {apiFetch} from "@/lib/api";

type Ui={language:string;response_language:string;code_block_wrap_long_lines?:boolean};
export default function StudentAccountSettings(){
 const [ui,setUi]=useState<Ui>();const [name,setName]=useState("");const [busy,setBusy]=useState(false);const [status,setStatus]=useState("");const [reload,setReload]=useState(0);
 useEffect(()=>{const controller=new AbortController();setUi(undefined);Promise.all([apiFetch("/api/heart/display",{signal:controller.signal,cache:"no-store"}),apiFetch("/api/auth/profile",{signal:controller.signal,cache:"no-store"})]).then(async responses=>{if(responses.some(r=>!r.ok))throw new Error();const [settings,profile]=await Promise.all(responses.map(r=>r.json()));if(!controller.signal.aborted){setUi(settings.ui??settings);setName(profile.username);setStatus("")}}).catch(()=>{if(!controller.signal.aborted)setStatus("无法读取账号和显示设置，请重试。")});return()=>controller.abort()},[reload]);
 async function save(event:React.FormEvent){event.preventDefault();if(!ui||busy)return;setBusy(true);setStatus("");try{const result=await apiFetch("/api/settings/ui",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({language:"zh",response_language:"zh",code_block_wrap_long_lines:ui.code_block_wrap_long_lines??false})});if(!result.ok)throw new Error();setStatus("显示设置已保存，刷新页面后应用。")}catch{setUi(undefined);setStatus("未能确认保存结果，请重新读取后核对。")}finally{setBusy(false)}}
 return <section aria-labelledby="student-account" className="mt-8 rounded-xl border border-border p-5">
  <h2 id="student-account" className="font-semibold">账号与显示设置</h2><p className="mt-2 text-sm">当前账号：{name||"正在读取"}。账号长期有效，登录会话会正常过期；密码重置请联系管理方。</p>
  <form onSubmit={save} className="mt-4 space-y-4"><p className="text-sm">界面语言：简体中文</p>
  <p className="text-sm">回答语言：简体中文</p>
  <label className="flex gap-2 text-sm"><input type="checkbox" disabled={!ui||busy} checked={ui?.code_block_wrap_long_lines??false} onChange={e=>setUi(ui?{...ui,code_block_wrap_long_lines:e.target.checked}:ui)}/>代码长行自动换行</label>
  <button type="submit" disabled={!ui||busy} className="rounded border border-border px-3 py-2 text-sm disabled:opacity-50">保存显示设置</button></form>
  {!ui&&<button type="button" onClick={()=>setReload(x=>x+1)} className="mt-3 underline">重新读取账号设置</button>}{status&&<p role="status" className="mt-3 text-sm">{status}</p>}
  <h3 className="mt-6 font-medium">教学偏好与生效范围</h3><p className="mt-2 text-sm text-muted-foreground">回答长度、举例、节奏和讲练顺序统一保存在我的记忆。长期记忆开启时用于后续辅导；关闭后不读取。本轮在聊天中明确提出的要求优先，不会自动改写长期偏好。</p><Link href="/memory" className="mt-3 inline-block text-sm underline">管理教学偏好</Link>
 </section>
}
