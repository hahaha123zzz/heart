import pytest

from integrations.deeptutor.course_scope import is_course_question


@pytest.mark.parametrize('message', [
    '今天几号', '现在几点', '你是谁', '你是什么模型', '怎么导出笔记', '登录密码忘了怎么办', '你好', 'hi',
])
def test_system_or_chitchat_messages_do_not_retrieve(message):
    assert is_course_question(message) is False


@pytest.mark.parametrize('message', [
    '自变量是什么', '什么是准实验设计', '第3章讲了什么', '教材里怎么定义信度',
    '为什么今天上课讲的那个实验要控制额外变量',
])
def test_course_messages_retrieve(message):
    assert is_course_question(message) is True


def test_blank_message_is_not_a_course_question():
    assert is_course_question('   ') is False
