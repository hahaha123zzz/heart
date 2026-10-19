"""关系对象沿用已有草稿事务及收据，独立核验有向关系语义。"""
import secrets
from uuid import uuid4
from sqlalchemy import select
from database.database import session_scope
from database.models import RelationRow, RelationOperationRow
from database.account_manager import AccountManager
from knowledge.course import get_section
from models.relation import RelationSpec
from visualization.truth_table import TruthTableService
from visualization.service import VisualizationError, digest
from visualization.relation_validator import ELEMENTS, PROPERTIES, TEMPLATES, template_spec, evaluate_relation, matrix
from knowledge.course_config import PSYCHOLOGY

POINT = 'legacy:relation' if PSYCHOLOGY else get_section(9,4)['title']
CLOSURE_POINT = 'legacy:closure' if PSYCHOLOGY else get_section(9,5)['title']


def target_key(snapshot):
    if snapshot.get('closure'):
        c=snapshot['closure']
        return 'relation:'+snapshot['artifact_id']+':closure:'+c['kind']+':'+str(c['step'])
    pair=snapshot.get('selected_pair')
    return 'relation:'+snapshot['artifact_id']+':'+snapshot['property']+(':'+pair['source']+pair['target'] if pair else '')


class RelationService(TruthTableService):
    operation_model = RelationOperationRow

    @staticmethod
    def allow_closure(row):
        if row.mode=='assessment' and row.submission is None:
            raise VisualizationError(403,'请先独立提交性质判断，再查看关系闭包')

    def closure_preview(self,artifact_id,request):
        from visualization.relation_closure import build_closure
        self.require_enabled(request.student_id)
        with session_scope() as session:
            row=self.load_row(session,artifact_id,request.student_id,request.session_id)
            if row.revision!=request.expected_revision:raise VisualizationError(409,'关系已变化，请重新打开闭包预览')
            self.allow_closure(row)
            return build_closure(RelationSpec.model_validate(row.spec),request.kind) | {
                'artifact_id':row.id,'revision':row.revision,'epoch':self.repo.memory_epoch(request.student_id,CLOSURE_POINT)}

    def capabilities(self, student_id):
        return {'enabled':self.enabled(student_id),'epoch':self.repo.memory_epoch(student_id,POINT),
                'templates':[{'id':key,'label':'关系示例 '+str(i+1)} for i,key in enumerate(TEMPLATES)],
                'properties':PROPERTIES}

    def load_row(self, session, artifact_id, student_id, session_id):
        row=session.scalar(select(RelationRow).where(RelationRow.id==artifact_id,
            RelationRow.student_id==student_id,RelationRow.session_id==session_id))
        if row is None or self.repo.memory_epoch(student_id,POINT)!=row.epoch:
            raise VisualizationError(404,'关系不存在、已删除或不属于当前会话')
        return row

    def public(self, row):
        spec=RelationSpec.model_validate(row.spec)
        return {'artifact_id':row.id,'conversation_id':row.conversation_id,'component_type':'relation',
                'schema_version':1,'origin':'auxiliary_example','knowledge_point':POINT,'elements':list(ELEMENTS),
                'pairs':row.spec['pairs'],'matrix':matrix(spec),'layout':row.layout,'revision':row.revision,
                'layout_revision':row.layout_revision,'mode':row.mode,'draft':row.draft,
                'correction_of':row.correction_of,'feedback':row.submission,'properties':PROPERTIES,
                'evaluation':evaluate_relation(spec) if row.mode=='explore' or row.submission else None,
                'readonly':not self.enabled(row.student_id)}

    def list(self, student_id, session_id):
        with session_scope() as session:
            rows=session.scalars(select(RelationRow).where(RelationRow.student_id==student_id,
                RelationRow.session_id==session_id).order_by(RelationRow.conversation_id.desc()).limit(40)).all()
            return [self.public(row) for row in rows if self.repo.memory_epoch(student_id,POINT)==row.epoch]

    def create(self, request):
        self.require_enabled(request.student_id)
        with session_scope(immediate=True) as session:
            fingerprint=digest(request.model_dump())
            old=session.scalar(select(RelationRow).where(RelationRow.student_id==request.student_id,
                RelationRow.session_id==request.session_id,RelationRow.request_id==request.request_id))
            if old and old.payload_hash!=fingerprint:
                raise VisualizationError(409,'同一请求编号不能用于不同内容')
            if self.repo.memory_epoch(request.student_id,POINT)!=request.expected_epoch:
                raise VisualizationError(409,'知识点记忆已变化，请重新打开关系示例')
            if old:return self.public(old)
            # 测评随机出题，不以固定模板名提前告知题型。
            spec=template_spec(secrets.choice(tuple(TEMPLATES)) if request.mode=='assessment' else request.template_id)
            layout={'a':{'x':150.,'y':55.},'b':{'x':65.,'y':210.},'c':{'x':235.,'y':210.}}
            draft={'values':dict.fromkeys(PROPERTIES),'explanation':''}
            if request.correction_of:
                original=self.load_row(session,request.correction_of,request.student_id,request.session_id)
                if original.submission is None:raise VisualizationError(409,'请先提交原判断，再开始订正')
                spec=RelationSpec.model_validate(original.spec);layout=original.layout;draft=original.draft
            AccountManager(self.repo).create_test_account(request.student_id);session.flush()
            message=self.repo.append_conversation(request.student_id,'assistant',
                '订正关系性质：修改原判断后提交，本次按辅助作答记录。' if request.correction_of else
                '关系图与矩阵辅助示例：A={a,b,c}。行是起点，列是终点；选中关系或性质可以提问。')
            row=RelationRow(id=str(uuid4()),student_id=request.student_id,session_id=request.session_id,
                conversation_id=message,knowledge_point=POINT,epoch=request.expected_epoch,request_id=request.request_id,
                payload_hash=fingerprint,spec=spec.model_dump(),layout=layout,mode=request.mode,correction_of=request.correction_of,
                revision=1,layout_revision=1,assisted=bool(request.correction_of) or request.mode=='explore',draft=draft)
            session.add(row)
            self.repo.record_event(request.student_id,'relation:'+row.id,POINT,'relation_created',
                {'artifact_id':row.id,'conversation_id':message,'correction_of':request.correction_of})
            session.flush();return self.public(row)

    @staticmethod
    def check_answers(row, request):
        if row.submission is not None:raise VisualizationError(409,'已提交，请点击订正这道题')
        if row.revision!=request.expected_revision:raise VisualizationError(409,'关系已变化，请重新加载')
        if set(request.values)!=set(PROPERTIES):raise VisualizationError(422,'请且仅填写当前五种性质')

    def operate(self, artifact_id, request):
        self.require_enabled(request.student_id)
        with session_scope(immediate=True) as session:
            row=self.load_row(session,artifact_id,request.student_id,request.session_id)
            fingerprint=digest(request.model_dump())
            old=session.scalar(select(RelationOperationRow).where(RelationOperationRow.artifact_id==artifact_id,
                RelationOperationRow.request_id==request.request_id))
            if old:
                if old.payload_hash!=fingerprint:raise VisualizationError(409,'同一操作编号不能用于不同内容')
                return old.result
            if row.revision!=request.expected_revision:raise VisualizationError(409,'关系已变化，请重新加载')
            if request.operation=='layout':
                if row.layout_revision!=request.expected_layout_revision:raise VisualizationError(409,'布局已变化，请重新加载')
                row.layout={key:value.model_dump() for key,value in request.positions.items()};row.layout_revision+=1
            else:
                if row.mode=='assessment' or row.submission:raise VisualizationError(409,'测评关系固定，请打开探索示例修改关系')
                pairs={(pair['source'],pair['target']) for pair in row.spec['pairs']}
                pair=(request.pair.source,request.pair.target)
                if request.present:pairs.add(pair)
                else:pairs.discard(pair)
                row.spec=RelationSpec(pairs=[{'source':a,'target':b} for a,b in sorted(pairs)]).model_dump()
                row.revision+=1
                # 改关系后旧预测不再对应当前实例。
                row.draft={'values':dict.fromkeys(PROPERTIES),'explanation':''}
            result=self.public(row)
            session.add(RelationOperationRow(id=str(uuid4()),artifact_id=row.id,request_id=request.request_id,
                payload_hash=fingerprint,result=result));session.flush();return result

    def submit(self, artifact_id, request):
        from memory.memory_manager import MemoryManager
        from memory.evidence_policy import assess_graph_attempt
        self.require_enabled(request.student_id)
        with session_scope(immediate=True) as session:
            row=self.load_row(session,artifact_id,request.student_id,request.session_id)
            fingerprint=digest(request.model_dump())
            if row.submission is not None:
                if row.submit_request_id==request.request_id and row.submit_payload_hash==fingerprint:return row.submission
                raise VisualizationError(409,'已提交，请点击订正这道题')
            self.check_answers(row,request)
            if any(value is None for value in request.values.values()):raise VisualizationError(422,'请判断全部五种性质')
            evaluation=evaluate_relation(RelationSpec.model_validate(row.spec));expected=evaluation['properties']
            checks={key:request.values[key]==value for key,value in expected.items()}
            row.draft=request.model_dump(include={'values','explanation'});decision=assess_graph_attempt(row.assisted)
            payload={'artifact_id':row.id,'revision':row.revision,'spec':row.spec,'answers':row.draft,
                'checks':checks,'expected':expected,'evaluation':evaluation,'assisted':row.assisted,
                'independent':decision.independent,'eligible':decision.eligible,'validator_version':evaluation['semantics']}
            event=MemoryManager(self.repo).record_relation_submission(request.student_id,POINT,row.id,payload,expected_epoch=row.epoch)
            row.submission=dict(payload,event_id=event,correct=all(checks.values()),explanation_verified=False,
                mastery_updated=False,step_advanced=False)
            row.submit_request_id=request.request_id;row.submit_payload_hash=fingerprint;row.revision+=1
            session.flush();return row.submission

    def snapshot(self, target, student_id, session_id, *, mark_assisted=True):
        self.require_enabled(student_id)
        with session_scope(immediate=True) as session:
            row=self.load_row(session,target.artifact_id,student_id,session_id)
            if row.revision!=target.expected_revision:raise VisualizationError(409,'关系已变化，请按最新版本提问')
            closure=None
            if target.closure:
                from visualization.relation_closure import build_closure
                self.allow_closure(row)
                preview=build_closure(RelationSpec.model_validate(row.spec),target.closure.kind)
                if target.closure.step>len(preview['steps']):raise VisualizationError(422,'闭包步骤不存在')
                step=preview['steps'][target.closure.step-1] if target.closure.step else None
                closure={'kind':target.closure.kind,'step':target.closure.step,'label':preview['label'],
                    'step_count':len(preview['steps']),'epoch':self.repo.memory_epoch(student_id,CLOSURE_POINT),
                    'current_pairs':step['after_pairs'] if step else preview['original_pairs'],
                    'reason':step['reason'] if step else '当前显示原关系，尚未补边。',
                    'added_pair':step['added_pair'] if step else None,'premises':step['premises'] if step else []}
            if mark_assisted and row.submission is None:row.assisted=True;session.flush()
            result={'artifact_id':row.id,'revision':row.revision,'epoch':row.epoch,'elements':list(ELEMENTS),
                'pairs':row.spec['pairs'],'property':target.property,'selected_pair':target.pair.model_dump() if target.pair else None,
                'evaluation':evaluate_relation(RelationSpec.model_validate(row.spec)),
                'answer_scope':'hint' if row.mode=='assessment' and row.submission is None else 'full'}
            if closure:result['closure']=closure
            return result

    def guard_snapshot(self, snapshot, student_id, session_id):
        self.require_enabled(student_id)
        with session_scope() as session:
            row=self.load_row(session,snapshot['artifact_id'],student_id,session_id)
            if row.revision!=snapshot['revision'] or row.epoch!=snapshot['epoch']:
                raise VisualizationError(409,'提问期间关系或作答已变化，请按当前实例重新提问')
            if snapshot.get('closure') and self.repo.memory_epoch(student_id,CLOSURE_POINT)!=snapshot['closure']['epoch']:
                raise VisualizationError(409,'闭包学习记忆已删除，请重新提问')
