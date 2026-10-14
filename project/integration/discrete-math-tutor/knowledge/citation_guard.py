"""核对明确编号单元紧邻的摘录引用，避免定理编号与跳转位置错配。"""
import re

UNIT = r'(?:定义|定理|引理|推论)\s*\d+\s*[.．]\s*\d+'


def citation_issues(response: str, excerpts: str) -> list[str]:
    headers = list(re.finditer(r'^\[(\d+)\] [^\n]*｜[^\n]*\n', excerpts, re.M))
    if not headers:
        return []
    units = {}
    for i, header in enumerate(headers):
        block = excerpts[header.end():headers[i+1].start() if i+1 < len(headers) else len(excerpts)]
        units[int(header.group(1))] = {
            re.sub(r'\s+', '', match).replace('．', '.') for match in re.findall(UNIT, block)}
    issues = []
    for match in re.finditer(r'(' + UNIT + r')[（(]?\s*\[(\d+)\]', response):
        unit = re.sub(r'\s+', '', match.group(1)).replace('．', '.')
        index = int(match.group(2))
        if unit not in units.get(index, set()):
            correct = [str(i) for i, refs in units.items() if unit in refs]
            hint = '；该编号出现在摘录[' + '、'.join(correct) + ']' if correct else '；当前摘录没有该编号'
            issues.append(f'{unit}[{index}]的引用编号与教材摘录不对应' + hint)
    return issues
