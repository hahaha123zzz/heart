"""教材与练习的兼容入口，内部统一检索当前学生完整历史。"""
from database.memory_index import memory_terms as terms


def selection_memory(memory, student_id, title, text, question, *,
                     selection_ref=None, question_id=None, version=None):
    return memory.retrieve_context(student_id,title=title,text=text,question=question,
        selection_ref=selection_ref,question_id=question_id,version=version)
