"""从真实教材/题库生成开发样例快照；标签待独立审核，不生成盲测成绩。"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    # 所有数据库相关模块导入前隔离，解析产生的裁图也留在临时目录。
    os.environ['DATABASE_URL']='sqlite:///:memory:'
    os.environ['LLM_MOCK']='1'
    from agents.task_context_builder import TaskContextBuilder
    from knowledge import pdf_reader
    from models.task_context import ExerciseTarget
    from practice_api import catalog
    with tempfile.TemporaryDirectory(prefix='intent-snapshots-') as folder:
        pdf_reader.CROPS=Path(folder)/'crops'
        record=pdf_reader.document('chapter-07')
        selection=pdf_reader.PDFSelection(document_id=record['document_id'],version=record['version'],kind='area',
            rects=[dict(page=4,x1=.12,y1=.16,x2=.88,y2=.43)])
        builder=TaskContextBuilder()
        pdf=builder.build(student_id='snapshot',message='snapshot',selection=selection).objects
        version=catalog()['version']
        exercise=builder.build(student_id='snapshot',message='snapshot',exercise_target=ExerciseTarget(
            question_id='ex-01-01-001',part_id='p1',version=version)).objects
        rows=[]

        def add(key,message,point,intents,*,objects=(),constraints=(),missing=(),flow='continue',move='question',needs=False,history=(),targets=None):
            rows.append(dict(id=key,conversation_id=key,template_family=key,split='development',
                source='agent_authored_project_snapshot',review_status='agent_reviewed_pending_human',
                input=dict(message=message,knowledge_point=point,history=list(history),known_points=[],
                    context=dict(objects=[obj.model_dump() for obj in objects],preferences={})),
                expected=dict(intent=flow,student_move=move,needs_context=needs),
                desired_task=dict(learning_intents=list(intents),answer_constraints=list(constraints),missing_slots=list(missing),
                    target_refs=list(targets) if targets is not None else [obj.id for obj in objects])))

        add('task-definition','什么是交集？','集合运算',['explain'])
        add('task-formula','A∧B什么时候为真？','命题逻辑',['explain'])
        add('task-proof','解释定理7.7的证明，并指出前置定理。','连通性',['proof'],constraints=['include_prerequisites'])
        add('task-sequence','先给一个例子，再解释定理7.7的证明。','连通性',['example','proof'],constraints=['example_before_proof'])
        add('task-pdf-hint','这段选区只给一个提示，不要完整答案。','图',['hint'],objects=pdf,
            constraints=['hint_only','no_full_answer'],needs=True)
        add('task-exercise-hint','当前小题只给提示，不要完整答案。','集合',['hint'],objects=exercise,
            constraints=['hint_only','no_full_answer'],needs=True)
        add('task-check','帮我检查当前小题的答案。','集合',['check_answer'],objects=exercise,needs=True)
        add('task-missing-target','这个为什么成立？','图',['proof'],flow='clarify_task',needs=True,missing=['target'])
        add('task-correction','不是并集，我问的是交集的定义。','集合运算',['explain'],
            history=[{'role':'assistant','content':'刚才解释了并集。'}])
        add('task-compare','比较欧拉路径和哈密顿路径，给两个例子。','图',['compare','example'])
        add('task-emotion','我很烦，但请给一个集合交集的例子。','集合运算',['example'])
        add('task-social','今天先到这里，下课吧。','图',[],flow='off_task',move='off_task')
        output=ROOT/'tests/data/intent/task12.jsonl'
        output.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
        audit={'cases':len(rows),'review_status':'pending_independent_review','split':'development',
            'pdf_source':{'document_id':selection.document_id,'version':selection.version,'rects':[r.model_dump() for r in selection.rects]},
            'exercise_source':{'question_id':'ex-01-01-001','part_id':'p1','version':version},
            'note':'服务端构建的上下文快照，不含裁图内容、学生数据或答案。不是盲测集；标签待独立审核。'}
        output.with_suffix('.audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'cases':len(rows),'output':str(output)},ensure_ascii=False))


if __name__=='__main__':
    main()
