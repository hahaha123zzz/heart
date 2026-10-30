"""已校验对象的来源和显式指向，拒绝引用不存在的ID。"""
import unittest
from models.chat_request import ChatRequest
from models.task_context import TaskContext,TaskObject
from agents.input_understanding.references import object_references,primary_reference,validated_choice


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


if __name__=='__main__':unittest.main()
