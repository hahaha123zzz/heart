"""技能估计从独立规则观测派生；重复小题只提供一份测量。"""
from sqlalchemy import select
from database.database import session_scope
from database.models import ExerciseSkillObservationRow, LearningEventRow
from knowledge.exercise_mapping import resolve_mapping, mapping_version, question_version
from knowledge.exercise_graders import evaluate_rule


class ExerciseSkillRepository:
    def record_exercise_skills(self, student_id, point, event_id, question_id, version, answers, output, assisted):
        with session_scope() as session:
            event=session.get(LearningEventRow,event_id)
            if not event or event.student_id != student_id or event.event_type != "exercise_submission":
                raise ValueError("技能观测缺少当前学生的练习事件")
            seen=set()
            for result in output.get("parts",[]):
                pid=result.get("part_id")
                if pid in seen or pid not in answers:
                    continue
                seen.add(pid)
                resolved=resolve_mapping(question_id,pid,version)
                if resolved is None:
                    continue
                mapping,part,key=resolved
                if point != mapping["source_point"]:
                    continue
                graded=evaluate_rule(part,answers[pid],key)
                verified=(result.get("method")=="rule" and result.get("confirmed") is True and
                    graded.get("confirmed") is True and result.get("score")==graded["score"] and
                    result.get("verdict")==graded["verdict"])
                eligible=verified and assisted is False
                score=graded["score"]/100 if verified else None
                reason="独立规则作答" if eligible else "获得提示或帮助，不能作为独立测量" if verified else "无法与服务器规则结果一致核验"
                exists=session.scalar(select(ExerciseSkillObservationRow.id).where(
                    ExerciseSkillObservationRow.event_id==event_id,ExerciseSkillObservationRow.part_id==pid))
                if exists is not None:
                    continue
                session.add(ExerciseSkillObservationRow(student_id=student_id,event_id=event_id,knowledge_point=point,
                    question_id=question_id,question_version=version,part_id=pid,skill_id=mapping["skill_id"],
                    skill_name=mapping["skill_name"],concept=mapping["concept"],mapping_version=mapping["mapping_version"],
                    score=score,eligible=eligible,outcome=graded["verdict"] if verified else "unknown",reason=reason,
                    diagnostic_targets=mapping["diagnostic_targets"] if eligible and score<1 else []))

    def skill_summary(self, student_id, point, limit=7):
        from knowledge.course_config import PSYCHOLOGY
        if PSYCHOLOGY:return []
        from practice_api import catalog
        revision=mapping_version();data=catalog();version=data["version"]
        if version != question_version(data["_catalog_source_version"]):
            return []
        with session_scope() as session:
            rows=session.scalars(select(ExerciseSkillObservationRow).where(
                ExerciseSkillObservationRow.student_id==student_id,ExerciseSkillObservationRow.knowledge_point==point,
                ExerciseSkillObservationRow.mapping_version==revision,ExerciseSkillObservationRow.question_version==version
                ).order_by(ExerciseSkillObservationRow.id)).all()
            # 按题号/小题保留最新有效观测；新 request_id 不能凭重复同题增加测量数。
            latest={}
            for row in rows:
                if row.eligible:
                    latest[(row.question_id,row.part_id)]=row
            groups={}
            for row in sorted(latest.values(),key=lambda r:r.id):
                item=groups.setdefault(row.skill_id,{"skill_id":row.skill_id,"name":row.skill_name,"concept":row.concept,
                    "mastery_estimate":.5,"assessment":"uncalibrated_skill_estimate","independent_items":0,
                    "needs_review":False,"diagnostic_targets":[],"sources":[],"last_observation_id":row.id})
                item["mastery_estimate"]=round(.6*item["mastery_estimate"]+.4*row.score,4)
                item["independent_items"]+=1
                item["needs_review"]=item["needs_review"] or row.score<1
                item["diagnostic_targets"]=list(dict.fromkeys(item["diagnostic_targets"]+row.diagnostic_targets))[:3]
                item["last_observation_id"]=row.id
                item["sources"].append({"event_id":row.event_id,"question_id":row.question_id,
                    "part_id":row.part_id,"version":row.question_version,"mapping_version":row.mapping_version,
                    "score":row.score,"verification":"rule_verified"})
                item["sources"]=item["sources"][-3:]
            return sorted(groups.values(),key=lambda i:(not i["needs_review"],-i["last_observation_id"]))[:limit]
