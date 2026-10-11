"""给现有索引添加逻辑公式表，不重建或修改向量。"""
import json
import sqlite3
from knowledge.hybrid_retrieval import INDEX
from knowledge.logic_formula import build_formula_index

if __name__ == "__main__":
    with sqlite3.connect(INDEX) as db:
        print(json.dumps(build_formula_index(db)))
