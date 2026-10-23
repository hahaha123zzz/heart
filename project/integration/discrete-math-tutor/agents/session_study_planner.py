"""需求→有界真实资料→现有 LLMPlanGenerator；本次约束不写长期画像。"""
from uuid import uuid4
import json
from models.session_study_plan import StudyRequest, StudyItem, SessionStudyPlan
from agents.q5_plan_generator import LLMPlanGenerator


def extract_request(llm, message, *, profile, path, previous=None):
    raw=llm.chat_json([
        {'role':'system','content':'''[AGENT:study_request]
从学生本次安排请求提取JSON，只允许goal,scope,time_budget_minutes,prior_knowledge,target_level,teaching_preference,practice_preference,assumptions。
goal为具体目标，scope为主题/章名字符串数组；没有主题且无既有路径时scope=[]，不得默认第一章。分钟数必须正整数，未给用null；一小时=60。prior_knowledge只记学生明确说的基础，不从语气猜。
practice_preference只允许none(只讲不要考试)、optional(未明确)、application(想练应用)。不明示的字段用空字符串；只缺时间可声明估算，不要求补问。
上一安排用于解释调整，最新明示优先：改成20分钟只学自变量要同步修改范围和预算；其余未变约束保留。这里只提取一次性需求，不修改长期画像。'''},
        {'role':'user','content':json.dumps({'message':message,'previous_request':previous,
            'confirmed_profile':profile,'confirmed_path_goal':path.get('goal','')},ensure_ascii=False)}],
        temperature=0,max_tokens=1200,retries=0)
    if not isinstance(raw,dict):
        raise ValueError('study_request_not_object')
    values=dict(raw)
    values['value_sources']={k:'explicit' for k,v in values.items() if v not in ('',None,[],{}) and k!='assumptions'}
    if not values.get('teaching_preference') and profile.get('teaching_preference'):
        values['teaching_preference']=profile['teaching_preference']
        values['value_sources']['teaching_preference']='confirmed_profile'
    if not values.get('goal') and path.get('goal'):
        values['goal']=path['goal'];values['value_sources']['goal']='confirmed_path'
    if not values.get('scope') and path.get('goal'):
        values['goal']=path['goal'];values['value_sources']['goal']='confirmed_path'
    if not values.get('goal'):
        values['goal']='本次学习安排（主题待确认）';values['value_sources']['goal']='assumption'
    if values.get('time_budget_minutes') is None:
        values.setdefault('assumptions',[]).append('未指定本次时长；各活动为预计用时，可调整，不代表实际学习时间。')
    return StudyRequest.model_validate(values)


def collect_materials(request, *, llm, status, guard):
    from knowledge.course_navigation import outline
    from knowledge.textbook import terms_for
    from knowledge.pdf_reader import document_for_chapter
    from agents.course_search import explicit_chapters, shared_search
    from agents.q3_navigation import LearningTarget, CallbackNavigator
    units=outline(); by_id={unit['id']:unit for unit in units}
    objectives=[obj for module in status.get('modules',[]) for obj in module.get('objectives',[])]
    owned={ref.get('unit_id'):obj['objective_id'] for obj in objectives for ref in obj.get('source_refs',[])}
    if not request.scope and owned:
        selected=[by_id[uid] for uid in owned if uid in by_id][:6]
    else:
        chapters=explicit_chapters(' '.join(request.scope) or request.goal)
        scopes=request.scope or [request.goal]
        selected=[]
        for topic in scopes:
            terms=terms_for(topic)
            ranked=sorted((u for u in units if not chapters or u['chapter_id'] in chapters),
                key=lambda u:(100 if topic in u['title'] else 0)+len(terms&terms_for(u['title']))*5+len(terms&terms_for(u.get('section_title',''))),reverse=True)
            for unit in ranked[:3]:
                score=(100 if topic in unit['title'] else 0)+len(terms&terms_for(unit['title']))*5+len(terms&terms_for(unit.get('section_title','')))
                if score>0 and unit not in selected:selected.append(unit)
        # 显式章导学可读取该章的有界样本，必须披露非整章覆盖。
        if not selected and chapters:selected=[u for u in units if u['chapter_id'] in chapters][:6]
        selected=selected[:6]
    materials=[];calls=[];chars=0
    for unit in selected:
        guard()
        search=shared_search(CallbackNavigator(),message=unit['title'],llm=llm)
        target=LearningTarget(unit['id'],unit['title'],unit['chapter_id'],unit['section_id'],version=unit['version'])
        rows=search.search(target=target,query=unit['title'],limit=2)
        calls.extend(search.calls)
        guard()
        text='\n'.join(row.quote or row.text for row in rows)[:2000]
        if not text or chars+len(text)>12000:continue
        record=document_for_chapter(unit['chapter_id'])
        ref={'source_kind':'q2_navigation','unit_id':unit['id'],'version':unit['version'],
             'document_id':record['document_id'],'chapter_id':unit['chapter_id'],
             'section_id':unit['section_id'],'title':unit['title'],'source_valid':unit.get('source_valid',True)}
        materials.append({'unit_id':unit['id'],'title':unit['title'],'source_ref':ref,
            'objective_id':owned.get(unit['id']),'text':text})
        chars+=len(text)
    return materials,calls


def generate_session(llm, request, *, scope, status, current, previous, materials, profile, validator, guard):
    available={m['unit_id']:m for m in materials}
    frozen=[i for i in (previous or {}).get('items',[]) if i['status'] in ('explained','done','skipped')]
    old_ids={(i['source_refs'][0]['unit_id'],i['kind']):i['item_id'] for i in (previous or {}).get('items',[])}
    feedback=''
    for attempt in range(2):
        guard()
        data=LLMPlanGenerator(llm).generate_session(request=request.model_dump(),materials=materials,profile=profile,
            frozen_items=frozen,feedback=feedback)
        guard()
        try:
            if not isinstance(data,dict) or set(data)-{'items','omitted'} or not isinstance(data.get('items'),list):
                raise ValueError('session_plan_response_invalid')
            items=[StudyItem.model_validate(i) for i in frozen]
            frozen_keys={(i.source_refs[0]['unit_id'],i.kind) for i in items}
            seen=set(frozen_keys)
            for raw in data['items']:
                raw=dict(raw);unit_id=raw.pop('unit_id');material=available.get(unit_id)
                if material is None:raise ValueError('session_plan_unknown_source')
                if set(raw)-{'kind','title','estimated_minutes','order_reason','completion_criterion'}:
                    raise ValueError('session_plan_model_cannot_set_identity_or_status')
                key=(unit_id,raw.get('kind'))
                if key in frozen_keys:continue
                if key in seen:raise ValueError('session_plan_duplicate_activity')
                seen.add(key)
                items.append(StudyItem(**raw,item_id=old_ids.get(key) or uuid4().hex,
                    objective_id=material['objective_id'],source_refs=[material['source_ref']]))
            if not items:raise ValueError('session_plan_empty')
            plan=SessionStudyPlan(plan_id=(previous or {}).get('plan_id') or uuid4().hex,
                revision=max((current or {}).get('revision',0),(previous or {}).get('revision',0))+1,
                student_id=scope.student_id,session_id=scope.session_id,course_id=scope.course_id,
                path_id=status.get('path_id'),path_revision=status.get('path_revision') if status.get('path_id') else None,
                base_plan_id=(current or {}).get('plan_id'),base_revision=(current or {}).get('revision',0),
                request=request,items=items,omitted=data.get('omitted',[]),
                source_binding={'coverage':'bounded_materials','unit_ids':list(available)})
            validator(plan.model_dump())
            return plan.model_dump()
        except (ValueError,TypeError,KeyError) as exc:
            feedback=str(exc)[:1000]
            if attempt:raise ValueError('session_plan_validation_failed: '+feedback) from exc
