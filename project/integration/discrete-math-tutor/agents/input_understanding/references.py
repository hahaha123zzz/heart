"""只从宿主校验的对象选择引用；历史背景不自动成为本轮显式目标。"""
from models.input_understanding import ObjectReference


def object_references(context):
    current=set(context.current_object_ids)
    return [ObjectReference(ref_id=f'object-{index}',kind=obj.kind,canonical_id=obj.id,
                status='resolved',origin='request' if obj.id in current else 'history',
                version=obj.version,title=obj.title)
            for index,obj in enumerate(context.objects)]


def primary_reference(context, request, references):
    expected=('pdf_selection' if request.selection or context.selection_scope else
              'exercise_part' if request.exercise_target else 'visualization' if request.visualization_target else
              'truth_table' if request.truth_table_target else 'relation' if request.relation_target else None)
    if expected is None:
        return None
    candidates=[r for r in references if r.kind==expected and r.status=='resolved' and
                (r.origin=='request' or expected=='pdf_selection' and context.selection_scope
                 and r.canonical_id==context.selection_scope.get('target_id'))]
    return candidates[0].ref_id if len(candidates)==1 else None


def validated_choice(ref_id, references):
    matches=[ref for ref in references if ref.ref_id==ref_id and ref.status=='resolved']
    if len(matches)!=1:
        raise ValueError('reference_not_in_validated_context')
    return matches[0]
