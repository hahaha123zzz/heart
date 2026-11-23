"use client";
import {browserStorage} from "@/shared/storage";
import {useEffect,useRef} from 'react';
import {usePathname,useSearchParams} from 'next/navigation';
import {useAuthStatus} from '@/hooks/useAuthStatus';
import type {PracticeRef,PracticeRating} from '@/lib/practice-api';
export type Submission={request_id:string;version:number;rating:PracticeRating;answer:string;self_report?:boolean};
export type PracticeRun={queue:PracticeRef[];index:number;total:number;saved:number;skipped:number;nextDue:number|null};
export function readRun(key:string|null):PracticeRun|null {
 if(!key)return null;
 try{const row=JSON.parse(browserStorage.readRaw("session",key)||'null');
  if(!row||!Array.isArray(row.queue)||row.queue.length>1000||!row.queue.length)return null;
  if(!row.queue.every((q:PracticeRef)=>Number.isSafeInteger(q.id)&&q.id>0&&(q.content_workspace_id===undefined||typeof q.content_workspace_id==='string')))return null;
  if(!['index','total','saved','skipped'].every(k=>Number.isSafeInteger(row[k])&&row[k]>=0)||row.index>row.queue.length||row.total>1000||row.saved+row.skipped>row.total)return null;
  if(row.nextDue!==null&&(!Number.isFinite(row.nextDue)||row.nextDue<0))return null;
  return row;
 }catch{return null;}
}
export function writeRun(key:string|null,row:PracticeRun|null){if(key)try{if(row)browserStorage.writeRaw("session",key,JSON.stringify(row));else browserStorage.removeRaw("session",key);}catch{/* 存储不可用仍可完成当前练习。 */}}
export function usePracticeRun(onResume:(items:PracticeRef[])=>void):string|null {
 const auth=useAuthStatus(),path=usePathname(),params=useSearchParams(),callback=useRef(onResume);callback.current=onResume;
 const query=new URLSearchParams(params.toString());query.sort();
 const key=auth.statusAvailable&&auth.userId?`heart-practice:${auth.userId}:${path}?${query}`:null;
 useEffect(()=>{const row=readRun(key);if(row&&row.index<row.queue.length)callback.current(row.queue);},[key]);
 return key;
}
export function readAnswer(key:string|null):{version:number;answer:string;submission:Submission|null}|null {
 if(!key)return null;
 try{const row=JSON.parse(browserStorage.readRaw("session",key)||'null');
  if(!row||!Number.isSafeInteger(row.version)||row.version<0||typeof row.answer!=='string'||row.answer.length>20000)return null;
  const s=row.submission;
  if(s&&(!/^[a-zA-Z0-9_-]{16,100}$/.test(s.request_id)||s.version!==row.version||s.answer!==row.answer||!['again','hard','good','easy'].includes(s.rating)))return null;
  return row;
 }catch{return null;}
}
export function writeAnswer(key:string|null,row:ReturnType<typeof readAnswer>){if(key)try{if(row)browserStorage.writeRaw("session",key,JSON.stringify(row));else browserStorage.removeRaw("session",key);}catch{/* 不向其他账号或共享存储回退。 */}}
