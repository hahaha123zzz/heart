"""真实模型多轮辅导验收；临时课程库、合成学生，每轮保存原始结果。"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--scenario",action="append")
    parser.add_argument("--cases",type=Path,default=ROOT/"tests/data/answer_flow/multiturn.json")
    args=parser.parse_args()
    cases=json.loads(args.cases.read_text(encoding="utf-8"))
    if args.scenario:
        if set(args.scenario)-{case["id"] for case in cases}:parser.error("未知场景")
        cases=[case for case in cases if case["id"] in args.scenario]
    if args.output.exists():parser.error("报告已存在，请另选文件名")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report={"method":"真实模型；API同一TaskService；同一学生每场景多轮连续对话；临时数据库；图解和后台记忆关闭；不等同教学收益或掌握校准", "scenarios":[]}
    failures=[]
    with tempfile.TemporaryDirectory(prefix="multiturn-feedback-") as directory:
        os.environ.update(TUTOR_COURSE="experimental-psychology-3",LLM_MOCK="0",MEMORY_WORKER_ENABLED="0",VISUALIZATION_ON_DEMAND="0",
            DATABASE_URL="sqlite:///"+str(Path(directory)/"legacy.db"),COURSE_DATABASE_URL="sqlite:///"+str(Path(directory)/"course.db"))
        sys.path.insert(0,str(ROOT))
        from database.database import engine
        assert engine.url.get_backend_name()=="sqlite" and Path(engine.url.database).resolve().parent==Path(directory).resolve()
        from llm.client import LLMClient
        calls=[];original=LLMClient.chat
        def measured(client,messages,*positional,**options):
            started=time.monotonic();system=str(messages[0].get("content",""))
            record={"agent":system.split("]")[0]+"]" if system.startswith("[AGENT:") else "course-model"}
            calls.append(record);options.setdefault("timeout",30)
            try:
                result=original(client,messages,*positional,**options)
                record["returned"]=True
                if record["agent"] in ("[AGENT:response_generator]","[AGENT:quality_checker]","[AGENT:conversation_router]","[AGENT:evidence_extractor]"):record["generated_text"]=result
                return result
            finally:record["seconds"]=round(time.monotonic()-started,3)
        LLMClient.chat=measured
        try:
            from main import _run_turn,orchestrator
            from models.chat_request import ChatRequest
            assert not orchestrator.llm.mock
            report.update(model=orchestrator.llm.model,mock=orchestrator.llm.mock)
            for case in cases:
                sid="multiturn-"+case["id"]
                orchestrator.memory.ensure_student(sid,account_type="production")
                orchestrator.memory.set_active_goal(sid,case["point"])
                scenario={"id":case["id"],"point":case["point"],"turns":[]};report["scenarios"].append(scenario)
                for turn in case["turns"]:
                    print("开始："+case["id"]+"/"+turn["id"],flush=True)
                    calls.clear();started=time.monotonic()
                    before=orchestrator.memory.get_state(sid,case["point"]).model_dump()
                    row={"id":turn["id"],"message":turn["message"],"required":turn["required"],"before":before}
                    try:
                        result=_run_turn(ChatRequest(student_id=sid,account_type="production",message=turn["message"],
                            learning_goal=case["point"],session_id=sid,request_id=sid+"-"+turn["id"]))
                        row["result"]=result
                        feedback=result.get("teaching_feedback") or {}
                        checks={"answered":result.get("answer_status")=="answered","feedback_mode":feedback.get("mode")==turn["mode"]}
                        if "hint_level" in turn:checks["hint_level"]=feedback.get("hint_level")==turn["hint_level"]
                        if turn["id"]!="first_error" and not turn.get("independent_attempt"):
                            checks["mastery_preserved"]=result.get("student_state",{}).get("mastery")==before["mastery"]
                            checks["step_not_advanced"]=not result.get("step_advanced")
                        row["checks"]=checks
                        if not all(checks.values()):failures.append(case["id"]+"/"+turn["id"])
                    except Exception as exc:
                        row["error_type"]=type(exc).__name__;failures.append(case["id"]+"/"+turn["id"])
                    row.update(seconds=round(time.monotonic()-started,3),model_calls=list(calls))
                    scenario["turns"].append(row)
                    report["failed_turns"]=list(failures)
                    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
                    print(json.dumps({"scenario":case["id"],"turn":turn["id"],"status":row.get("result",{}).get("answer_status"),
                        "feedback":row.get("result",{}).get("teaching_feedback"),"checks":row.get("checks"),"seconds":row["seconds"]},ensure_ascii=False),flush=True)
        finally:
            LLMClient.chat=original;engine.dispose()
    if failures:raise SystemExit(1)


if __name__=="__main__":main()
