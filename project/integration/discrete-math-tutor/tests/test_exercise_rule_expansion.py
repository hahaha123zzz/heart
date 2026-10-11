"""新增答案规则的独立数学核验与真实批改链路验证。"""
import itertools
import json
import math
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select
import practice_api as practice
from database.database import session_scope
from database.models import ExerciseSubmissionRow
from knowledge.exercise_graders import evaluate_rule
from knowledge.exercise_mapping import fingerprint
from tests import test_exercise_skills as fixtures

REVIEW=Path(__file__).resolve().parents[1]/"knowledge/exercises/rule_review.json"

def reviewed():return json.loads(REVIEW.read_text(encoding="utf8"))["items"]

class RuleMathReviewTests(unittest.TestCase):
    def check_values(self,qid,expected):
        for pid,value in expected.items():
            self.assertEqual(practice.keys()[qid][pid]["expected"],value,(qid,pid))

    def test_set_judgements_using_actual_nested_sets_and_counterexample(self):
        empty=frozenset();ab=frozenset({"a","b"});abc=frozenset({"a","b","c"})
        outer=frozenset({"a","b","c",abc});nested=frozenset({ab,frozenset({ab})})
        values=[empty<=empty,empty in empty,empty<=frozenset({empty}),empty in frozenset({empty}),
            ab<=outer,ab in outer,ab<=nested,ab in nested]
        self.check_values("ex-01-01-007",{"p"+str(i+1):str(v).lower() for i,v in enumerate(values)})
        A=frozenset({1});B=frozenset({A});C=B
        self.assertTrue(A in B and B<=C);self.assertFalse(A<=C)
        self.check_values("ex-01-01-007",{"p9":"true","p10":"false"})

    def test_restriction_properties_for_every_relation_on_three_elements(self):
        S=set(range(3));pairs=list(itertools.product(S,repeat=2))
        def trans(R):return all((x,z) in R for x,y in R for y2,z in R if y==y2)
        def order(R,S):return trans(R) and all((x,x) in R for x in S) and all(x==y or (y,x) not in R for x,y in R)
        def total(R,S):return order(R,S) and all((x,y) in R or (y,x) in R for x in S for y in S)
        def well(R,S):
            return total(R,S) and all(any(all((x,y) in R for y in T) for x in T)
                for n in range(1,len(S)+1) for T in itertools.combinations(S,n))
        for mask in range(1<<len(pairs)):
            R={p for i,p in enumerate(pairs) if mask&(1<<i)}
            for size in range(4):
                for sub in itertools.combinations(S,size):
                    T=set(sub);restricted={(x,y) for x,y in R if x in T and y in T}
                    for fn in [lambda r,s:trans(r),order,total,well]:
                        if fn(R,S):self.assertTrue(fn(restricted,T))
        self.check_values("ex-09-03-012",{"p"+str(i):"true" for i in range(1,5)})

    def test_inclusion_exclusion_with_concrete_population(self):
        first=set(range(26));second=set(range(12,33));both=len(first&second)
        self.assertEqual(len(first),26);self.assertEqual(len(second),21)
        self.assertEqual(50-len(first|second),17)
        # 3 人三队、9 人两队、46 人一队的可行构造。
        football=set(range(3))|set(range(3,12))|set(range(12,38))
        basketball=set(range(3))|set(range(3,9))|set(range(38,44))
        volleyball=set(range(3))|set(range(9,12))|set(range(44,58))
        self.assertEqual([len(x) for x in [football,basketball,volleyball]],[38,15,20])
        two=sum(sum(i in t for t in [football,basketball,volleyball])==2 for i in range(58))
        swim=set(range(85));run=set(range(60))|set(range(85,150))
        self.assertEqual(len(swim&run),60);self.assertEqual(len(swim|run),150)
        self.check_values("ex-03-01-002",{"p1":[str(both)],"p2":[str(two)],"p4":[str(len(run))]})

    def test_pair_and_parity_counts_by_enumeration(self):
        self.check_values("ex-03-02-002",{
            "p1":[str(len(list(itertools.combinations(range(50),2)))),str(sum(a!=b for a,b in itertools.product(range(50),repeat=2)))],
            "p2":[str(sum((a+b)%2==1 for a,b in itertools.combinations(range(1,11),2)))],
            "p3":[str(sum((a+b)%2==0 for a,b in itertools.product(range(1,7),repeat=2)))]})

    def test_degree_lower_bound_has_attaining_graph(self):
        edges={tuple(sorted((i,(i+1)%9))) for i in range(9)}|{(0,3),(1,4),(2,5)}
        degrees=[sum(i in e for e in edges) for i in range(9)]
        self.assertEqual(len(edges),12);self.assertEqual(degrees.count(3),6)
        self.assertEqual(degrees.count(2),3)
        self.check_values("ex-07-01-002",{"p1":[str(6+math.ceil((2*len(edges)-6*3)/2))]})

    def test_bounds_and_review_fingerprints(self):
        self.check_values("ex-09-03-002",{"p3":[str(min([5,7,9])),str(max([5,7,9]))]})
        self.assertEqual(len(reviewed()),22)
        for item in reviewed():
            q=practice.question(item["question_id"]);p=next(p for p in q["parts"] if p["id"]==item["part_id"])
            k=practice.keys()[q["id"]][p["id"]]
            self.assertEqual(item["fingerprint"],fingerprint(q,p,k));self.assertTrue(item["derivation"])
            self.assertNotIn('"image"',json.dumps(p))
            if k["kind"]=="numeric_fill":self.assertEqual(p["blank_count"],len(k["expected"]))

    def test_numeric_equivalence_partial_and_unsupported_format(self):
        q=practice.question("ex-03-02-002");p=q["parts"][0];key=practice.keys()[q["id"]][p["id"]]
        for a in [["50*49/2","50*49"],["1225.0","24500/10"]]:
            out=evaluate_rule(p,a,key);self.assertEqual(out["score"],100);self.assertTrue(out["confirmed"])
        self.assertEqual(evaluate_rule(p,["1225","0"],key)["score"],50)
        self.assertFalse(evaluate_rule(p,["共有1225次","2450"],key)["confirmed"])

class ExtendedSkillWorkerTests(unittest.TestCase):
    setUp=fixtures.ExerciseSkillTests.setUp
    tearDown=fixtures.ExerciseSkillTests.tearDown
    submit=fixtures.ExerciseSkillTests.submit

    def test_all_new_questions_use_real_rule_worker_without_ai(self):
        groups={}
        for item in reviewed():groups.setdefault(item["question_id"],{})[item["part_id"]]=item["expected"]
        main=SimpleNamespace(orchestrator=SimpleNamespace(memory=self.memory))
        for qid,answers in groups.items():
            sub=uuid4().hex
            with session_scope() as session:
                session.add(ExerciseSubmissionRow(id=sub,student_id="s",request_id=sub,question_id=qid,
                    version=self.version,answers=answers,status="queued",result={"_memory_epoch":0}))
            with patch.dict("sys.modules",{"main":main}),patch.object(practice,"ai_parts",side_effect=AssertionError("规则题不得调用 AI")):
                practice.run_submission(sub)
            with session_scope() as session:
                row=session.get(ExerciseSubmissionRow,sub)
                self.assertEqual(row.status,"completed");self.assertEqual(row.result["confirmed_score"],100)
            point=practice.question(qid)["knowledge_point"]
            self.assertTrue(self.memory.skill_summary("s",point))
            self.assertEqual(self.memory.get_state("s",point).mastery,.5)

    def test_extended_questions_keep_existing_api_contract(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app=FastAPI();app.include_router(practice.router)
        main=SimpleNamespace(orchestrator=SimpleNamespace(memory=self.memory))
        qid="ex-03-02-002"
        with patch.dict("sys.modules",{"main":main}),patch.object(practice,"student",return_value="s"),patch.object(practice,"ai_parts",side_effect=AssertionError("不得调用 AI")):
            with TestClient(app) as client:
                question=client.get(f"/api/practice/questions/{qid}",params={"student_id":"s"})
                self.assertEqual(question.status_code,200)
                parts=question.json()["question"]["parts"]
                self.assertEqual(parts[0]["grader"],"rule");self.assertEqual(parts[3]["grader"],"ai_assisted")
                self.assertNotIn('"expected"',json.dumps(question.json()["question"]))
                base={"student_id":"s","version":self.version,"request_id":uuid4().hex}
                invalid=client.post(f"/api/practice/questions/{qid}/submit",json=dict(base,answers={"p1":["1225"]}))
                self.assertEqual(invalid.status_code,422)
                stale=client.post(f"/api/practice/questions/{qid}/submit",json=dict(base,version="0"*64,answers={"p1":["1225","2450"]}))
                self.assertEqual(stale.status_code,409)
                sent=client.post(f"/api/practice/questions/{qid}/submit",json=dict(base,answers={"p1":["50*49/2","50*49"]}))
                self.assertEqual(sent.status_code,200);self.assertEqual(sent.json()["result"],{})
                graded=client.get("/api/practice/submissions/"+sent.json()["id"],params={"student_id":"s"}).json()
                self.assertEqual(graded["status"],"completed");self.assertEqual(graded["result"]["confirmed_score"],100)
                self.assertNotIn("_memory_epoch",graded["result"])
                retry=client.post(f"/api/practice/questions/{qid}/submit",json=dict(base,answers={"p1":["50*49/2","50*49"]}))
                self.assertEqual(retry.json()["id"],sent.json()["id"])

    def test_new_wrong_skill_is_scoped_and_assisted_answer_is_excluded(self):
        qid="ex-07-01-002";point=practice.question(qid)["knowledge_point"]
        self.submit({"p1":["8"]},qid=qid)
        item=self.memory.skill_summary("s",point)[0]
        self.assertEqual(item["skill_id"],"graph.degree_lower_bound")
        self.assertAlmostEqual(item["mastery_estimate"],.3);self.assertTrue(item["needs_review"])
        self.submit({"p1":["9"]},qid=qid,assisted=True)
        self.assertAlmostEqual(self.memory.skill_summary("s",point)[0]["mastery_estimate"],.3)
        self.assertEqual(self.memory.skill_summary("other",point),[])
        self.assertEqual(self.memory.get_misconceptions("s",point),[])

if __name__=="__main__":unittest.main()
