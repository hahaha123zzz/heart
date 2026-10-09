"""仅检索当前学生与本次教材选区相关的学习记忆。"""
import re

def terms(text):
    clean = re.sub(r'[^\w\u4e00-\u9fff]', '', text.casefold())
    return {clean[i:i+2] for i in range(len(clean)-1) if not clean[i:i+2].isdigit()}

def selection_memory(memory, student_id, title, text, question):
    target = terms(title+' '+text[:600]+' '+question)
    def score(value): return len(target & terms(value))
    points = sorted(memory.list_learning_points(student_id),key=score,reverse=True)
    relevant = [p for p in points if score(p)>=2 or p==title][:3]
    states, evidence = [], []
    for point in relevant:
        state = memory.get_state(student_id,point)
        states.append({'point':point,'mastery':state.mastery,'remaining_gap':state.remaining_gap[:300],
            'summary':state.last_summary[:300],'misconceptions':[m.model_dump() for m in state.misconceptions if m.status!='resolved'][:3]})
        evidence.extend(memory.list_evidence(student_id,point)[-3:])
    history = memory.get_history(student_id)
    related = [m for m in history if score(m.get('content',''))>=2][-6:]
    history_refs = memory.repo.get_conversation_with_figures(student_id,limit=12)
    related += [{'role':m['role'],'content':m['content'][:1000]} for m in history_refs
                if (m.get('selection_ref') or {}).get('section_title')==title][-4:]
    related = [dict(t) for t in {str(m):m for m in related}.values()][-6:]
    profile = memory.get_profile(student_id)
    return {'preferences':profile.preferences,'learning_states':states,
            'evidence':[{k:str(v)[:350] for k,v in e.items() if k not in ('student_id',)} for e in evidence[-6:]],
            'related_history':related,
            'summary':('参考 '+str(len(states))+' 个相关知识点的学习记录' if states else '暂无相关知识点学习记录')+'；按你的讲解偏好回答'}
