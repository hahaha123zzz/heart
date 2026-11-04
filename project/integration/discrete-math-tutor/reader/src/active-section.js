// 按阅读页内位置找最近的小节标题；页码使用教材原始页码。
export function activeSection(sections, fallback, page, y) {
 const list=(sections||[]).filter(s=>Number.isInteger(s.page)&&s.id!=null);
 let active=list[0];
 for(const section of list){
  if(section.page<page||(section.page===page&&(Number(section.y)||0)<=y+.01))active=section;
  else break;
 }
 return active?.id ?? fallback?.id ?? fallback;
}
