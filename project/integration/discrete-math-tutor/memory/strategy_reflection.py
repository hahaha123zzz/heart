"""规则反思，借鉴来源绑定与经验库；不制造自然语言因果结论。"""
from collections import defaultdict


def summarize(rows):
    groups=defaultdict(list)
    for row in rows:
        if row["instructional_move"]:
            groups[(row["instructional_move"],row["difficulty"],row["hint_level"])].append(row)
    result=[]
    for (move,difficulty,hint),items in groups.items():
        progress=sum(r["outcome"]=="progress" for r in items)
        regression=sum(r["outcome"]=="regression" for r in items)
        measured=progress+regression
        result.append({"instructional_move":move,"difficulty":difficulty,"hint_level":hint,
            "progress":progress,"regression":regression,"unknown":len(items)-measured,"measured":measured,
            "weight":round(.5+.1*(progress-regression)/measured,3) if measured>=3 else None,
            "source_observation_ids":[r["id"] for r in items[-5:]],
            "source_event_ids":[r["observation_event_id"] for r in items[-5:]],
            "reflection":f"同条件下 {progress} 次估计进展、{regression} 次估计回落、{len(items)-measured} 次未知；不能据此证明教学因果效果",
            "verification":"ai_provisional"})
    return sorted(result,key=lambda item:(item["measured"],item["source_observation_ids"][-1]),reverse=True)[:6]
