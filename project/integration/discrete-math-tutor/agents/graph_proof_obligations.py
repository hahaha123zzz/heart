"""删边连通性讲解的完整性检查，不是形式化证明器。"""
import re


def missing_connectivity_obligation(response):
    if not re.search(r'删(?:去|除|掉)?|移除|[TGH]\s*[-−]\s*e', response):
        return None
    claim = None
    for clause in re.split(r'[。；！\n]', response):
        match = re.search(r'(?:[TGH](?:\s*[-−]\s*e)?|图|原图|整张图|整个图|顶点)(?:仍然|仍|依然|保持)(?:是)?连通|(?:删去|删除|移除)[^，,]{0,20}(?:保持|仍然|仍)连通', clause)
        if match:
            prefix = re.split(r'[，,]', clause[:match.start()])[-1]
            if re.search(r'若|如果|假设|反设|不能|不代表|不足|并不|错误|无法', prefix + match.group(0)):
                continue
            claim = match.group(0)
            break
    if not claim:
        return None
    endpoints = bool(re.search(r'(?:e|边).{0,6}(?:两端|端点)|e\s*=\s*\{[^}]+\}', response))
    arbitrary = bool(re.search(r'(?:任意|任取|任一)(?:两个|两|一对)?(?:点|顶点)|(?:任意|任取|任一).{0,12}(?:通路|路径)|所有.{0,8}(?:通路|路径)', response))
    replacement = bool(re.search(r'替换|代替|取代|替代|改走|换成', response)) and bool(re.search(r'通路|路径|游走', response))
    if endpoints and arbitrary and replacement:
        return None
    missing = []
    if not endpoints:
        missing.append('写明被删边的两个端点，以及连接它们的绕行通路')
    if not arbitrary:
        missing.append('明确讨论任意两点的原通路，而不是只讨论反证中的一对点')
    if not replacement:
        missing.append('说明原通路经过该边时用绕行通路替换，不经过则保留')
    return claim, '删边连通性讲解完整性检查未通过：' + '；'.join(missing)
