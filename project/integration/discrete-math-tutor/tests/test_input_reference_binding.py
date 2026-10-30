"""已校验对象的来源和显式指向，拒绝引用不存在的ID。"""
import unittest
from models.chat_request import ChatRequest
from models.task_context import TaskContext,TaskObject
from agents.input_understanding.references import object_references,primary_reference,validated_choice,collect_objects,introduced_objects
from unittest.mock import Mock


class ReferenceBindingTests(unittest.TestCase):
    def test_history_selection_is_not_an_explicit_new_question_target(self):
        obj=TaskObject(id='selection:old',kind='pdf_selection',title='旧选区',chapter_id=1,section_id=1)
        context=TaskContext(student_id='s',message='什么是因变量',objects=[obj])
        refs=object_references(context)
        self.assertEqual(refs[0].origin,'history')
        self.assertIsNone(primary_reference(context,ChatRequest(message=context.message),refs))

    def test_valid_bound_selection_can_be_restored(self):
        obj=TaskObject(id='selection:old',kind='pdf_selection',title='旧选区',chapter_id=1,section_id=1)
        context=TaskContext(student_id='s',message='再通俗一点',objects=[obj],selection_scope={'target_id':obj.id})
        refs=object_references(context)
        self.assertEqual(primary_reference(context,ChatRequest(message=context.message),refs),'object-0')
        self.assertEqual(validated_choice('object-0',refs).canonical_id,obj.id)
        with self.assertRaises(ValueError):validated_choice('other-student-object',refs)

    def test_current_reader_section_does_not_force_a_concrete_question_target(self):
        obj=TaskObject(id='section:1:1',kind='section',title='章节背景',chapter_id=1,section_id=1)
        context=TaskContext(student_id='s',message='这个实验？',objects=[obj],current_object_ids=[obj.id])
        refs=object_references(context)
        self.assertEqual(refs[0].origin,'request')
        self.assertIsNone(primary_reference(context,ChatRequest(message=context.message),refs))

    def test_saved_spans_have_stable_identity_and_epoch_is_checked(self):
        text='例子一：调节光照。\n\n实验案例：比较两个教学条件。'
        row=dict(id='turn1',student_id='s',session_id='tab',epoch=0,knowledge_point='变量',
                 result=dict(answer_status='answered',reply=text))
        memory=Mock();memory.memory_epoch.return_value=0
        refs=collect_objects([row],memory,'s','tab')
        self.assertEqual([r.kind for r in refs],['example','experiment'])
        for ref in refs:
            self.assertEqual(text[ref.span[0]:ref.span[1]],ref.quote)
        self.assertEqual(refs,introduced_objects('turn1',text))
        self.assertEqual(collect_objects([row],memory,'s','other'),[])
        memory.memory_epoch.return_value=1
        self.assertEqual(collect_objects([row],memory,'s','tab'),[])

    def test_introductory_disclaimer_is_not_registered_as_an_example(self):
        refs=introduced_objects('turn','下面用两个日常场景说明（教学示例，非原书例题）。\n\n例子一：安排不同光照。\n\n例子二：安排不同睡眠。')
        self.assertEqual([r.kind for r in refs],['assistant_claim','example','example'])

    def test_explicit_figure_uses_existing_verified_catalog_identity(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from agents.input_understanding.service import understand
        context=TaskContext(student_id='s',message='解释图1-4')
        figure=SimpleNamespace(id='real-figure',sha256='a'*64,label='图1-4 科学研究过程')
        with patch('knowledge.figures.retrieve_figures',return_value=[figure]):
            turn=understand(context,ChatRequest(student_id='s',message=context.message))
        self.assertEqual(turn.tasks[0].target_ref,'figure-0')
        self.assertEqual(turn.references[0].canonical_id,'real-figure')

    def test_explicit_figure_does_not_validate_unrelated_images(self):
        from unittest.mock import patch
        from knowledge.figures import retrieve_figures
        other=Mock(kind='figure',label='图2-3');other.is_valid.return_value=True
        target=Mock(kind='figure',label='图1-4');target.is_valid.return_value=True
        with patch('knowledge.figures.load_figures',return_value=[other,target]), \
             patch('knowledge.figures._visual_kinds',return_value={'figure'}):
            self.assertEqual(retrieve_figures('解释图1-4',[]),[target])
        other.is_valid.assert_not_called()
        target.is_valid.assert_called_once()

    def test_saved_figure_followup_binds_the_verified_same_asset(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from agents.input_understanding.service import understand
        media={'id':'image-1','sha256':'f'*64,'document_id':'doc','version':'v'}
        row=dict(id='turn',student_id='s',session_id='tab',epoch=0,knowledge_point='目标',
                 result=dict(answer_status='answered',reply='图的说明',image_refs=[media]))
        figure=SimpleNamespace(id='image-1',sha256='f'*64,label='图5-2',chapter_id=5)
        memory=Mock();memory.memory_epoch.return_value=0
        with patch('knowledge.figures.get_figure',return_value=figure), \
             patch('knowledge.pdf_reader.document_for_chapter',return_value={'document_id':'doc','version':'v'}):
            refs=collect_objects([row],memory,'s','tab',include_media=True)
        context=TaskContext(student_id='s',session_id='tab',message='刚才那张图再解释一下',reference_objects=refs)
        turn=understand(context,ChatRequest(student_id='s',session_id='tab',message=context.message))
        ref=next(r for r in turn.references if r.ref_id=='mention')
        self.assertEqual((ref.kind,ref.canonical_id),('figure','image-1'))
        self.assertEqual(turn.tasks[0].target_ref,'mention')


if __name__=='__main__':unittest.main()
