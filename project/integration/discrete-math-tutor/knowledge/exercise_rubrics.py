"""按题型制定的评分项；未知标准答案均标记为待复核。"""
RUBRICS={
 'proof':[('conditions','明确使用题目条件和证明目标',20),('reasoning','各步推导有效且说明依据',50),('conclusion','结论成立、关键情况与量词无遗漏',30)],
 'graph':[('structure','图满足题目的结构和性质',60),('representation','顶点、边、方向及标记明确',20),('completeness','完成题目要求的其他构造或说明',20)],
 'matrix':[('structure','维度和行列含义符合题意',20),('entries','矩阵元素或真值正确',60),('completeness','结果与题目要求完整对应',20)],
 'expression':[('expression','数学表达式符合题意',50),('calculation','计算与变换正确',30),('conditions','定义域、边界与其他必要条件完整',20)],
 'written':[('answer','回答题目要求且结论正确',50),('reasoning','解释与依据有效',30),('completeness','覆盖全部要求',20)],
 'fill':[('answer','各空的数学含义与答案正确，接受等价形式',100)],
 'choice':[('answer','选项与题意正确对应，检查原题歧义',100)],
 'judgement':[('answer','真伪判断正确',100)],
}
def grading_spec(part,verified=False):
 return {'review_status':'verified' if verified else 'needs_review','criteria':[{'id':i,'label':label,'max_score':weight} for i,label,weight in RUBRICS[part['type']]],'instruction':'仅核查原题要求；没有要求推导时，可由答案本身体现评分项。原题歧义或图像模糊时不作确定判分。'}
