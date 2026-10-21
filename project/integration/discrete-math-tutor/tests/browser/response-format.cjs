/* 现有 Markdown 的实际增量切片与标准格式夹具；不调用模型。 */
const {chromium}=require('playwright');
const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const root=process.env.UX_PROJECT||path.resolve(__dirname,'../..');const output=process.env.UX_OUTPUT;
const report={checks:[]};
(async()=>{const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
try{const page=await browser.newPage({viewport:{width:375,height:812}});
await page.setContent('<meta charset="utf-8"><main style="width:100%;max-width:640px"></main>');
await page.addStyleTag({path:path.join(root,'frontend/pdf-reader/reader.css')});
await page.addStyleTag({path:path.join(root,'frontend/tutor-markdown/tutor-markdown.css')});
await page.addScriptTag({path:path.join(root,'frontend/tutor-markdown/tutor-markdown.js')});
const samples=[
 ['heading_list','## 学习要点\n\n1. **自变量**：主动改变的条件。\n2. ==因变量==：观察的反应。[1]'],
 ['table','| 变量 | 含义 | 单位 |\n|---|---|---|\n| 自变量 | 操纵条件 | 次 |\n| 因变量 | 反应时间 | ms |\n\n注：这是排版夹具。'],
 ['math','行内 $DL=kI$。\n\n$$\\frac{a+b}{c}=\\sqrt{x}$$'],
 ['code','```python\nvalue = "[1]"\nprint(value)\n```'],
 ['chinese','中文**“关键条件”**，中文**（控制变量）**。'],
 ['invalid_math','错误公式 $\\unknown{x}$ 后文仍可读。'],
 ['long_plan',Array.from({length:11},(_,i)=>`## 第 ${i+1} 章\n\n- 学习目标 ${i+1}\n- 教材来源与活动 ${i+1}`).join('\n\n')],
 ['unsafe','<script>alert(1)</script>\n\n[危险](javascript:alert(1))\n\n![外部](https://example.org/a.png)'],
];
const baseline=process.env.UX_BASELINE;
if(baseline){const events=fs.readFileSync(baseline,'utf8').split(/\r?\n/).filter(s=>s.startsWith('data: ')).map(s=>{try{return JSON.parse(s.slice(6))}catch{return null}});const answer=events.reverse().find(e=>e?.reply);if(answer)samples.push(['actual_baseline',answer.reply]);}
for(const [name,text] of samples){const result=await page.evaluate(({name,text})=>{
 const host=document.querySelector('main');let readable=true;
 for(let n=1;n<=text.length;n++){host.innerHTML=TutorMarkdown.render(text.slice(0,n),{streaming:true});if(!host.textContent.trim()&&/\p{L}/u.test(text.slice(0,n)))readable=false;}
 const incremental=TutorMarkdown.render(text,{streaming:true});host.innerHTML=incremental;
 const settled=TutorMarkdown.render(text);const replay=TutorMarkdown.render(text);
 const result={readable,sameBody:incremental.replace('streaming','settled')===settled,replay:settled===replay,
  h2:host.querySelectorAll('h2').length,table:host.querySelectorAll('tbody tr').length,math:host.querySelectorAll('.katex').length,displayMath:host.querySelectorAll('.katex-display').length,
  strong:host.querySelectorAll('strong').length,unsafe:!!host.querySelector('script,img,a[href^="javascript:"]'),text:host.textContent,
  overflow:document.documentElement.scrollWidth>innerWidth+1};return result;
},{name,text});
report.checks.push({name,...result});
assert.ok(result.readable,`${name}: 增量正文不可消失`);assert.ok(result.sameBody&&result.replay,`${name}: 完成/历史一致`);assert.ok(!result.unsafe&&!result.overflow,`${name}: 安全与窄屏`);
if(name==='table')assert.equal(result.table,2);if(name==='math'){assert.equal(result.math,2);assert.equal(result.displayMath,1);}if(name==='chinese')assert.equal(result.strong,2);if(name==='long_plan')assert.equal(result.h2,11);
report.checks.at(-1).passed=true;}
await page.evaluate(()=>document.querySelector('main').innerHTML=TutorMarkdown.render('## 比较变量\n\n| 变量 | 条件与观察 |\n|---|---|\n| 自变量 | **主动改变**的条件[1] |\n| 因变量 | 测量的反应 |\n\n$$DL=kI$$'));
if(output)await page.screenshot({path:output+'/format-mobile.png',fullPage:true});
}finally{if(output)fs.writeFileSync(output+'/format.json',JSON.stringify(report,null,2));await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
