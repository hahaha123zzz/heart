from knowledge.psychology_retrieval import _query_concepts


def test_query_concepts_remove_question_wording():
    assert _query_concepts("随机区组设计是什么？") == ["随机区组设计"]
    assert _query_concepts("什么是单因素随机区组设计") == ["单因素随机区组设计"]
