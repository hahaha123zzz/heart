import re

STRONG_TERMS = {
    "单射","满射","双射",
    "子集","真子集",
    "合取","析取","否定",
    "充分必要","充分","必要",
    "当且仅当",
    "自反","反自反","对称","反对称","传递",
    "有向边","无向边",
}
WEAK_TERMS = {"集合","关系","函数","映射","等价","划分","偏序","哈斯图","有限","无限","连通"}

SYNONYMS = {
    "入射":"单射",
    "一对一":"单射",
    "一一对应":"双射",
    "一一映射":"双射",
    "与":"合取",
    "或":"析取",
    "非":"否定",
}

NEG_PATTERN = re.compile(r"并不是|不是|反例|例题|证明", re.MULTILINE)


def normalize_terms(s: str, use_syn: bool = True) -> str:
    s = s.strip()
    if use_syn:
        for ori, std in SYNONYMS.items():
            if ori in s:
                s = s.replace(ori, std)
    return s


def extract_strong(s: str, use_syn: bool = True):
    s = normalize_terms(s, use_syn)
    return {w for w in STRONG_TERMS if w in s}


def extract_weak(s: str, use_syn: bool = True):
    s = normalize_terms(s, use_syn)
    return {w for w in WEAK_TERMS if w in s}


def get_dynamic_threshold(query: str) -> float:
    L = len(query)
    if L <= 8:
        return 0.40
    elif L <= 20:
        return 0.50
    else:
        return 0.45


def fuzzy_score(query: str, text: str):
    q_norm = normalize_terms(query)
    t_norm = normalize_terms(text)

    if NEG_PATTERN.search(text):
        return 0.0

    q_strong = extract_strong(q_norm)
    t_strong = extract_strong(t_norm)
    q_weak = extract_weak(q_norm)
    t_weak = extract_weak(t_norm)

    if len(q_strong) > 0 and len(q_strong - t_strong) > 0:
        return 0.0

    strong_match = len(q_strong) / max(len(q_strong), 1)
    weak_match = len(q_weak & t_weak) / max(len(q_weak), 1)

    if len(q_strong) == 0:
        score = weak_match
    else:
        score = 0.8 * strong_match + 0.2 * weak_match
    return min(max(score, 0.0), 1.0)


DOCS = [
    {"id":1,"text":"集合由若干元素组成，元素具有确定性、互异性、无序性。"},
    {"id":2,"text":"单射：不同自变量对应不同函数值；满射：值域等于陪域；双射既是单射又是满射。"},
    {"id":3,"text":"自反关系：每个元素都和自己有关系；反自反：任何元素都不和自己有关系。"},
    {"id":4,"text":"对称关系：若aRb则bRa；反对称：若aRb且bRa则a=b。"},
    {"id":5,"text":"传递关系：若aRb、bRc，则一定有aRc。"},
]


def exact_search(query: str):
    qn = normalize_terms(query)
    res = []
    for d in DOCS:
        if qn in normalize_terms(d["text"]):
            res.append(d)
    return res


def hybrid_search(q: str):
    exact_res = exact_search(q)
    if len(exact_res) > 0:
        return exact_res, "exact"

    thresh = get_dynamic_threshold(q)
    scored = []
    for d in DOCS:
        s = fuzzy_score(q, d["text"])
        if s >= thresh:
            scored.append((d, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in scored], "fuzzy"


def rerank(candidate_list, query: str):
    qs = extract_strong(normalize_terms(query))
    res = []
    for doc in candidate_list:
        ds = extract_strong(normalize_terms(doc["text"]))
        boost = 0.12 if qs & ds else 0
        res.append((doc, boost))
    res.sort(key=lambda x:x[1], reverse=True)
    return [d for d,_ in res]


if __name__ == "__main__":
    test_data = [
        ("什么是单射？", [2]),
        ("入射是什么", [2]),
        ("自反关系定义", [3]),
        ("对称和反对称关系", [4]),
        ("传递关系是什么", [5]),
        ("集合的特点", [1]),
        ("什么是满射？", [2]),
        ("什么是哈斯图？", []),
    ]
    sum_prec = 0.0
    sum_recall = 0.0
    sum_f1 = 0.0
    print(f"{'Query':<22}{'相关id':<12}{'返回id列表':<22}{'Precision':<10}{'Recall':<10}{'F1'}")
    print("-"*85)
    for q, gold_ids in test_data:
        raw, branch = hybrid_search(q)
        res = rerank(raw, q)
        pred_ids = [x["id"] for x in res]
        rel = set(gold_ids)
        pred = set(pred_ids)
        tp = len(rel & pred)

        # ========== 就是这里！替换这一块 ==========
        if len(rel) == 0:
            if len(pred) == 0:
                prec = 1.0
                rec = 1.0
            else:
                prec = 0.0
                rec = 1.0
        elif len(pred) == 0:
            prec = 0.0
            rec = 0.0
        else:
            prec = tp / len(pred)
            rec = tp / len(rel)

        if prec + rec == 0:
            f1 = 0.0
        else:
            f1 = 2 * prec * rec / (prec + rec)
        # =========================================

        sum_prec += prec
        sum_recall += rec
        sum_f1 += f1
        print(f"{q:<22}{str(gold_ids):<12}{str(pred_ids):<22}{prec:.4f}{rec:.4f}{f1:.4f}")
    n = len(test_data)
    print("-"*85)
    print(f"平均Precision = {sum_prec/n:.4f} | 平均Recall = {sum_recall/n:.4f} | 平均F1 = {sum_f1/n:.4f}")
