"""只从宿主校验的对象选择引用；历史背景不自动成为本轮显式目标。"""
from models.input_understanding import ObjectReference
import hashlib
import re


def introduced_objects(turn_id, text):
    """只登记明确的例子段与可定位回答片段；不把段落猜作实验实体。"""
    objects = []
    for match in re.finditer(r'[^\n]+(?:\n(?!\n)[^\n]+)*', text):
        quote = match[0][:1200]
        if not quote.strip() or quote.lstrip().startswith('#'):
            continue
        marked = r'^\s*[*#> -]*(?:%s)(?:[（(][^）)]{0,30}[）)])?[*\s]*[：:]'
        experiment = re.search(marked % r'实验示例|实验案例|实验[一二三四1234]', quote)
        example = (re.search(marked % r'教学示例|例子[一二三四1234]?|举例', quote)
                   or re.search(r'例如[，,:：]|比如[，,:：]|比如你|例如你|举个例子[，：:]|打个比方[，：:]', quote))
        kind = 'experiment' if experiment else 'example' if example else 'assistant_claim'
        end = match.start() + len(quote)
        digest = hashlib.sha256(quote.encode()).hexdigest()
        objects.append(ObjectReference(ref_id='history-' + digest[:12], kind=kind,
            canonical_id=f'turn:{turn_id}:{match.start()}:{end}:{digest[:12]}', status='resolved',
            origin='history', introduced_turn_id=turn_id, version=digest,
            title=quote.replace('\n', ' ')[:100], quote=quote, span=[match.start(), end]))
    return objects[-8:]


def collect_objects(recent, memory_repo, student_id, session_id, *, include_media=False):
    """从仍有效、同会话、同 epoch 的真实发布回答重建有限引用，不信任保存的模型 ID。"""
    result, epochs = [], {}
    for row in reversed(recent):
        if (row.get('student_id') != student_id or row.get('session_id') != session_id
                or (row.get('result') or {}).get('answer_status') != 'answered'):
            continue
        point = row['knowledge_point']
        if point not in epochs:
            epochs[point] = memory_repo.memory_epoch(student_id, point)
        if epochs[point] != row['epoch']:
            continue
        if include_media:
            from knowledge.figures import get_figure
            from knowledge.pdf_reader import document_for_chapter
            for media in row['result'].get('image_refs') or []:
                figure = get_figure(str(media.get('id') or ''))
                record = document_for_chapter(figure.chapter_id) if figure else None
                if (figure and record and media.get('sha256') == figure.sha256
                        and media.get('document_id') == record['document_id']
                        and media.get('version') == record['version']):
                    result.append(ObjectReference(ref_id='history-figure-'+hashlib.sha256(figure.id.encode()).hexdigest()[:12],
                        kind='figure',canonical_id=figure.id,status='resolved',origin='history',
                        introduced_turn_id=row['id'],version=figure.sha256,title=figure.label[:200]))
        text = str(row['result'].get('reply') or '')
        for obj in introduced_objects(row['id'], text):
            if obj.canonical_id not in {r.canonical_id for r in result}:
                result.append(obj)
        if len(result) >= 8:
            break
    return result[:8]


def guard_bound_objects(turn, repository, memory_repo):
    """发布边界复核历史片段身份及删除 epoch；不重新解释内容或读取整本教材。"""
    from database.learning_tasks import TaskConflict, now
    used = {task.target_ref for task in turn.tasks}
    checked = set()
    for ref in turn.references:
        if ref.ref_id not in used or not ref.introduced_turn_id or ref.canonical_id in checked:
            continue
        row = repository.get(turn.context.student_id, turn.context.session_id, ref.introduced_turn_id)
        if (row['status'] != 'completed' or row['expires_at'] <= now()
                or memory_repo.memory_epoch(row['student_id'], row['knowledge_point']) != row['epoch']):
            raise TaskConflict('reference_stale', '所引用的历史片段已失效，本轮不再发布。')
        text = str((row.get('result') or {}).get('reply') or '')
        if ref.kind == 'figure':
            from knowledge.figures import get_figure
            from knowledge.pdf_reader import document_for_chapter
            figure = get_figure(ref.canonical_id)
            record = document_for_chapter(figure.chapter_id) if figure else None
            matches = [m for m in (row.get('result') or {}).get('image_refs', [])
                       if m.get('id') == ref.canonical_id and m.get('sha256') == ref.version]
            if (not figure or figure.sha256 != ref.version or not record or not matches
                    or matches[0].get('document_id') != record['document_id']
                    or matches[0].get('version') != record['version']):
                raise TaskConflict('reference_stale', '所引用的教材图片已失效，请重新选择。')
            checked.add(ref.canonical_id)
            continue
        quote = text[ref.span[0]:ref.span[1]] if ref.span else ''
        if quote != ref.quote or hashlib.sha256(quote.encode()).hexdigest() != ref.version:
            raise TaskConflict('reference_stale', '所引用的回答片段已经变化，请重新选择。')
        checked.add(ref.canonical_id)


def bind_mention(turn, context, request):
    text = turn.envelope.raw_text
    mention = re.search(r'(?:刚才|前面|之前|这个|那个|上个|上面|这张|那张|这幅|那幅).{0,5}(?:例子|示例|实验|图|说法|结论|那句话|这句话)', text)
    if not mention or request.selection or request.exercise_target or context.selection_scope:
        return turn
    kind = ('figure' if '图' in mention[0] else 'experiment' if '实验' in mention[0] else
            'example' if re.search(r'例子|示例', mention[0]) else 'assistant_claim')
    candidates = [r for r in context.reference_objects if r.kind == kind]
    # “刚才”只在最近一个引入轮次内解析；同轮两个例子仍需选择。
    if candidates:
        latest = candidates[0].introduced_turn_id
        candidates = [r for r in candidates if r.introduced_turn_id == latest][:4]
    if len(candidates) == 1:
        ref = ObjectReference.model_validate(candidates[0].model_dump() | {'ref_id': 'mention'})
    else:
        ref = ObjectReference(ref_id='mention', kind=kind, status='ambiguous' if candidates else 'missing',
            candidate_ids=[r.canonical_id for r in candidates], origin='history', title=mention[0])
    value = turn.model_dump()
    value['references'] = [*value['references'], ref.model_dump()]
    for task in value['tasks']:
        if task['action'] in ('explain_content', 'provide_hint', 'discuss_claim', 'compare_content'):
            task['target_ref'] = 'mention'
    value['resolution_status'] = 'resolved' if candidates and len(candidates) == 1 else 'ambiguous' if candidates else 'missing'
    from models.input_understanding import GroundedTurn
    return GroundedTurn.model_validate(value)


def object_references(context):
    current=set(context.current_object_ids)
    return [ObjectReference(ref_id=f'object-{index}',kind=obj.kind,canonical_id=obj.id,
                status='resolved',origin='request' if obj.id in current else 'history',
                version=obj.version,title=obj.title)
            for index,obj in enumerate(context.objects)]


def figure_references(request):
    from knowledge.figures import FIGURE_NUMBER, retrieve_figures
    if not FIGURE_NUMBER.search(request.message) or request.selection:
        return []
    return [ObjectReference(ref_id=f'figure-{index}',kind='figure',canonical_id=figure.id,
                status='resolved',origin='request',version=figure.sha256,title=figure.label[:200])
            for index,figure in enumerate(retrieve_figures(request.message,[],limit=2))]


def primary_reference(context, request, references):
    expected=('pdf_selection' if request.selection or context.selection_scope else
              'exercise_part' if request.exercise_target else 'visualization' if request.visualization_target else
              'truth_table' if request.truth_table_target else 'relation' if request.relation_target else None)
    if expected is None:
        figures=[r for r in references if r.kind=='figure' and r.origin=='request' and r.status=='resolved']
        return figures[0].ref_id if len(figures)==1 else None
    candidates=[r for r in references if r.kind==expected and r.status=='resolved' and
                (r.origin=='request' or expected=='pdf_selection' and context.selection_scope
                 and r.canonical_id==context.selection_scope.get('target_id'))]
    return candidates[0].ref_id if len(candidates)==1 else None


def validated_choice(ref_id, references):
    matches=[ref for ref in references if ref.ref_id==ref_id and ref.status=='resolved']
    if len(matches)!=1:
        raise ValueError('reference_not_in_validated_context')
    return matches[0]
