import {test} from 'node:test';
import assert from 'node:assert/strict';
import {activeSection} from './active-section.js';
const sections=[{id:1,page:1,y:.42},{id:2,page:2,y:.48},{id:3,page:5,y:.62}];
test('按页码与页内纵坐标跟随最近的小节标题',()=>{
 assert.equal(activeSection(sections,{id:2},1,0),1);
 assert.equal(activeSection(sections,{id:1},1,.43),1);
 assert.equal(activeSection(sections,{id:1},2,.2),1);
 assert.equal(activeSection(sections,{id:1},2,.5),2);
 assert.equal(activeSection(sections,{id:2},5,.7),3);
 assert.equal(activeSection(sections,{id:3},9,.1),3);
});
test('没有页内目录时保留当前小节',()=>{
 assert.equal(activeSection([],{id:4},3,.2),4);
 assert.equal(activeSection(undefined,3,1,0),3);
});
