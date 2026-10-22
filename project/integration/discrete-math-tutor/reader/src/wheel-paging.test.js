import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createWheelPaging} from './wheel-paging.js';
function fixture(){
 let time=0,blocked=false;const turns=[];
 const wheel=createWheelPaging(n=>turns.push(n),()=>blocked,()=>time);
 return {turns,block:b=>blocked=b,event:(deltaY=120,dt=10,extra={})=>{
  time+=dt;let prevented=false;
  wheel({deltaY,deltaX:0,deltaMode:0,cancelable:true,preventDefault(){prevented=true;},...extra});return prevented;
 }};
}
test('连续手势及长惯性只翻一页，空闲后可反向翻页',()=>{
 const f=fixture();for(let i=0;i<100;i++)assert(f.event(12,25));
 assert.deepEqual(f.turns,[1]);f.event(-120,281);assert.deepEqual(f.turns,[1,-1]);
});
test('小幅累计、方向切换、行与页单位',()=>{
 const f=fixture();f.event(2);f.event(2);f.event(-3);assert.deepEqual(f.turns,[]);
 f.event(-5);f.event(1,281,{deltaMode:1});f.event(-1,281,{deltaMode:2});
 assert.deepEqual(f.turns,[-1,1,-1]);
});
test('修饰键、横向、不可取消、选区不翻页且不拦截',()=>{
 const f=fixture();for(const extra of [{ctrlKey:true},{metaKey:true},{shiftKey:true},{deltaX:150},{cancelable:false}])assert.equal(f.event(120,300,extra),false);
 f.block(true);assert.equal(f.event(),false);assert.deepEqual(f.turns,[]);
 f.block(false);f.event(120,300);assert.deepEqual(f.turns,[1]);
});
test('首尾仍消耗整个手势，防止原生滚动或重复触发',()=>{
 const f=fixture();f.event(-120);f.event(120);assert.deepEqual(f.turns,[-1]);
});
test('圈选结束后的同一手势惯性不会突然翻页',()=>{
 const f=fixture();f.block(true);f.event();f.block(false);f.event();assert.deepEqual(f.turns,[]);
 f.event(120,281);assert.deepEqual(f.turns,[1]);
});
