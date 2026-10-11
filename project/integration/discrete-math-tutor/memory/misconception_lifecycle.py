"""借鉴来源链与受约束记忆变更：反证是提议，状态迁移是本地规则。"""
from __future__ import annotations
import hashlib
import re
from models.misconception import Misconception, normalize_type
from memory.evidence_policy import source_quote

AI_COUNTER_REQUIRED = 2  # 初始工程阈值，不是诊断准确率保证
ACTIVE = {"hypothesis", "supported", "confirmed"}


def quote_hash(quote):
    normalized=re.sub(r"\s+", "", quote).casefold()
    return hashlib.sha256(normalized.encode()).hexdigest()


def useful_quote(item,message):
    quote=source_quote(item,message)
    if re.fullmatch(r"(?:我)?(?:懂了|明白了|理解了|会了|知道了|好的|嗯|谢谢)[，。！!\s]*",quote):
        return ""
    return quote


def apply_updates(memory,student_id,point,event_id,message,decision,hypotheses,corrections):
    repo=memory.repo
    existing=memory.get_misconceptions(student_id,point)
    by_id={m.id:m for m in existing}
    supports={}
    for hypo,merge_id in hypotheses:
        quote=useful_quote(hypo,message)
        if not quote:
            continue
        normalized=normalize_type(hypo.type) or hashlib.sha256(hypo.description.encode()).hexdigest()
        target=by_id.get(merge_id) or next((m for m in existing if normalize_type(m.type)==normalized),None)
        key=target.id if target else normalized
        supports.setdefault(key,(target,hypo,quote,normalized))
    proposals={}
    results=[]
    for update in corrections:
        target=by_id.get(update.misconception_id)
        base={"misconception_id":update.misconception_id,"action":update.action}
        quote=useful_quote(update,message)
        if target is None:
            results.append(base|{"outcome":"rejected","reason":"目标不属于当前学生和知识点"});continue
        if not decision.independent or not decision.eligible or not quote or not update.reason.strip():
            results.append(base|{"outcome":"rejected","reason":"没有可追溯的独立作答反证"});continue
        if target.status not in ACTIVE:
            results.append(base|{"outcome":"inactive","reason":"误区已处于非活跃状态"});continue
        proposals.setdefault(target.id,[]).append((update,quote))

    def observe(target,action,outcome,quote,reason,before):
        evidence_type="misconception" if action=="support" else "misconception_conflict" if action=="conflict" else "misconception_counter"
        evidence_id=repo.add_event_evidence(event_id,point,evidence_type,reason,
            .9 if decision.verification=="rule_verified" else .6, "misconception-change:"+str(target.id),
            verification=decision.verification,independent=decision.independent,source_quote=quote,misconception_id=target.id)
        repo.record_misconception_observation(student_id,target.id,event_id,evidence_id,
            action,outcome,before,target.status,quote_hash(quote),reason)
        return {"misconception_id":target.id,"action":action,"outcome":outcome,
            "before_status":before,"after_status":target.status,"evidence_id":evidence_id,"reason":reason}

    conflicts={mid for mid,values in proposals.items() if mid in supports or len({v[0].action for v in values})>1}
    for mid in conflicts:
        target=by_id[mid];quote=proposals[mid][0][1]
        results.append(observe(target,"conflict","conflict",quote,"本轮支持与反证或纠正意图互相冲突，保持状态",target.status))

    if decision.independent and decision.eligible:
        for key,(target,hypo,quote,normalized) in supports.items():
            if key in conflicts:
                continue
            target=target or Misconception(knowledge_point=point,type=normalized,description=hypo.description)
            before=target.status
            reopened=target.status not in ACTIVE
            if reopened:
                target.status="hypothesis";target.evidence_count=0
            target.add_supporting_evidence(hypo.confidence)
            target=repo.save_misconception(student_id,target)
            results.append(observe(target,"support","reopened" if reopened else "supported",quote,hypo.description,before))

    for mid,values in proposals.items():
        if mid in conflicts:
            continue
        target=by_id[mid];update,quote=values[0];before=target.status
        if update.action=="dismiss" and target.status=="confirmed":
            results.append({"misconception_id":mid,"action":"dismiss","outcome":"review_required",
                "reason":"已确认误区不能由自动驳回提议直接取消"});continue
        votes=repo.misconception_counter_votes(student_id,mid,update.action)
        count=len(votes|{quote_hash(quote)})
        accepted=decision.verification=="rule_verified" or count>=AI_COUNTER_REQUIRED
        if accepted:
            target.resolve() if update.action=="resolve" else target.dismiss()
            repo.save_misconception(student_id,target)
        outcome=target.status if accepted else "pending"
        record=observe(target,update.action,outcome,quote,update.reason,before)
        results.append(record|{"distinct_counter_evidence":count,"required":1 if decision.verification=="rule_verified" else AI_COUNTER_REQUIRED})
    return results
