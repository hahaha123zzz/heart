"""课程问题判定：决定本轮是否必须先检索教材。

顺序固定：先课程线索（命中即课程问题），再系统类负向类别，其余默认课程问题。
"""
from __future__ import annotations

import re

COURSE_HINTS = re.compile(
    r"教材|课本|课程|第[一二三四五六七八九十\d]+章|定义|概念|原理|理论|实验|变量|自变量|因变量|"
    r"信度|效度|样本|被试|假设|测量|统计|心理学|知觉|记忆|注意|情绪|动机|人格|社会认知|"
    r"神经|脑区|感觉|学习|思维|语言|发展"
)

SYSTEM_PATTERNS = (
    re.compile(r"今天|明天|昨天|现在几点|几号|星期几|日期|今年|几点"),
    re.compile(r"你是谁|你叫什么|你是什么模型|你是哪家|谁开发|你的名字"),
    re.compile(r"怎么用|怎么导出|怎么登录|密码|设置在哪|界面|按钮|注册|退出登录|付费|订阅|更新|安装"),
    re.compile(r"^(?:你好|您好|嗨|在吗|早上好|中午好|晚上好|hi|hello)[!！。~～\s]*$", re.IGNORECASE),
)


def is_course_question(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    if COURSE_HINTS.search(text):
        return True
    return not any(pattern.search(text) for pattern in SYSTEM_PATTERNS)
