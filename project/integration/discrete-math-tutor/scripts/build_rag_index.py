"""构建教材的结构索引；可选生成本地中文语义向量。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from array import array
from pathlib import Path

from knowledge.structured_index import build_records
from knowledge.textbook import terms_for
from knowledge.logic_formula import build_formula_index

INDEX = Path(__file__).resolve().parents[1] / "knowledge" / "rag_index_v2.sqlite3"
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


def build_index(target: Path = INDEX, *, embed: bool = False, model_name: str = DEFAULT_MODEL) -> dict:
    records = build_records()
    model = None
    if embed:
        from fastembed import TextEmbedding
        from knowledge.semantic_chunks import refine

        model = TextEmbedding(model_name=model_name, cuda=False)
        records = refine(records, model)
    reusable: dict[str, tuple[str, str, bytes]] = {}
    if model is not None and target.is_file():
        try:
            with sqlite3.connect(target) as previous:
                old_model = previous.execute("SELECT value FROM metadata WHERE key='embedding_model'").fetchone()
                if old_model and old_model[0] == model_name:
                    reusable = {
                        chunk_id: (section, text, vector)
                        for chunk_id, section, text, vector in previous.execute(
                            "SELECT c.id,c.section,c.text,v.data FROM chunks c JOIN vectors v ON c.id=v.id"
                        )
                    }
        except sqlite3.DatabaseError:
            reusable = {}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".building.sqlite3")
    if temporary.exists():
        temporary.unlink()
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript("""
            CREATE TABLE chunks (
                id TEXT PRIMARY KEY, parent_id TEXT, chapter_id INTEGER,
                source TEXT, section TEXT, section_id INTEGER, page INTEGER,
                block_start INTEGER, block_end INTEGER, kind TEXT,
                text TEXT, asset_ids TEXT
            );
            CREATE VIRTUAL TABLE chunks_fts USING fts5(id UNINDEXED, tokens);
            CREATE TABLE vectors (id TEXT PRIMARY KEY, data BLOB NOT NULL);
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX idx_chunks_parent ON chunks(parent_id);
            CREATE INDEX idx_chunks_chapter ON chunks(chapter_id, section_id);
        """)
        for item in records:
            connection.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                item["id"], item["parent_id"], item["chapter_id"], item["source"],
                item["section"], item["section_id"], item["page"],
                item["block_start"], item["block_end"], item["kind"],
                item["text"], json.dumps(item["asset_ids"], ensure_ascii=False),
            ))
            tokens = terms_for(item["source"] + " " + item["section"] + " " + item["text"])
            connection.execute("INSERT INTO chunks_fts VALUES (?,?)", (item["id"], " ".join(sorted(tokens))))
        connection.execute("INSERT INTO metadata VALUES ('count',?)", (str(len(records)),))
        if model is not None:
            missing = []
            for item in records:
                previous = reusable.get(item["id"])
                if previous and previous[:2] == (item["section"], item["text"]):
                    connection.execute("INSERT INTO vectors VALUES (?,?)", (item["id"], previous[2]))
                else:
                    missing.append(item)
            contents = [item["section"] + "\n" + item["text"][:1600] for item in missing]
            for item, vector in zip(missing, model.embed(contents, batch_size=32)):
                connection.execute("INSERT INTO vectors VALUES (?,?)", (item["id"], array("f", vector).tobytes()))
            connection.execute("INSERT INTO metadata VALUES ('embedding_model',?)", (model_name,))
        build_formula_index(connection)
        connection.commit()
    except BaseException:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    connection.close()
    temporary.replace(target)
    return {"chunks": len(records), "embedding_model": model_name if embed else None,
            "index": str(target)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed", action="store_true", help="用 FastEmbed 生成语义向量")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    print(json.dumps(build_index(embed=args.embed, model_name=args.model), ensure_ascii=False))
