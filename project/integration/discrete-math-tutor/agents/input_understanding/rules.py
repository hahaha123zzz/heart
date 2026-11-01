"""仅解析明确表达，保留原话、否定与字符位置。"""
import re


RESUME = re.compile(r'(?:回到|返回).{0,6}(?:题|检查)|继续(?:答题|刚才的题)|再(?:看|出).{0,4}(?:题|检查)')
NEGATED_RESUME = re.compile(r'(?:不要|不用|别|先不|不必|无需).{0,3}(?:回到|返回|继续答|再看|再出)')
EXPLAIN = re.compile(r'(?:先)?(?:请)?(?:解释|讲解|说明)(?:一下)?\s*[“「\"‘]?(.+?)'
                     r'[”」\"’]?(?:这个词|这个概念|一词)?[，,；;]?\s*(?:再|然后)(?:回到|返回|继续答题)')
NEGATED_CHOICE = re.compile(r'(?:不选|不是|不认为|不能选|排除|并非|没选|没决定|没有选择|还没选|不要选)\s*[A-Za-z]')
QUESTION = re.compile(r'[？?]|为什么|为何|怎么|如何|解释|选项.*(?:意思|区别)')
MULTIPLE_CHOICE = re.compile(r'(?<![A-Za-z])[A-D]\s*(?:或|还是|或者|/|和)\s*[A-D](?![A-Za-z])')


def normalize(raw):
    text, positions = [], []
    for index, char in enumerate(raw):
        if char.isspace():
            if text and text[-1] != ' ':
                text.append(' '); positions.append(index)
        else:
            text.append(char); positions.append(index)
    if text and text[-1] == ' ':
        text.pop(); positions.pop()
    return ''.join(text), positions


def resume_requested(text):
    return bool(RESUME.search(text) and not NEGATED_RESUME.search(text))


def only_resume_requested(text):
    """Replay permits only a bound question and explicit presentation modifiers."""
    return bool(resume_requested(text) and re.fullmatch(
        r'(?:请|现在)?(?:回到|返回)(?:原来|刚才|上面|原)?的?(?:那道|这道|原)?(?:题|小?检查)'
        r'(?:[，,；;]\s*(?:请)?(?:原样(?:显示|重现)(?:题目|题干|原题)?|不要(?:给|透露)(?:出)?(?:参考)?答案|我还没作答)){0,3}'
        r'[。！!\s]*', text))


def explanation_before_resume(text):
    match = EXPLAIN.search(text)
    if not match or not resume_requested(text):
        return None
    return re.sub(r'[“”「」\"‘’]', '', match[1]).strip(' ，,；;')


def choice_submission(text, options):
    from agents.deeptutor_learning.pending import is_readable_choice_answer, resolve_choice_submission
    if NEGATED_CHOICE.search(text) or QUESTION.search(text) or MULTIPLE_CHOICE.search(text):
        return ''
    return resolve_choice_submission(text, options) if is_readable_choice_answer(text, options) else ''


def non_submission(text):
    return bool(NEGATED_CHOICE.search(text) or QUESTION.search(text) or MULTIPLE_CHOICE.search(text) or re.search(
        r'不要替我作答|还没作答|不是提交|先插问|另外问', text))
