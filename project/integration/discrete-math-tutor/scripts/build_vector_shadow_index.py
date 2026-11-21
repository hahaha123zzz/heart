"""Copy the active RAG index and add embeddings without rebuilding its source."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from array import array
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "knowledge/rag_index_v2.sqlite3"
TARGET = ROOT / ".runtime/vector-retrieval-shadow-v1.sqlite3"


def build(source: Path, target: Path, model_name: str, cache_dir: str | None = None) -> dict:
    if source.resolve() == target.resolve():
        raise ValueError("实验索引不能覆盖正式索引")
    if not source.is_file():
        raise FileNotFoundError(source)
    temporary = target.with_suffix(".building.sqlite3")
    temporary.unlink(missing_ok=True)
    shutil.copy2(source, temporary)

    from fastembed import TextEmbedding

    kwargs = {"cuda": False}
    if cache_dir:
        kwargs["cache_dir"] = cache_dir
    model = TextEmbedding(model_name=model_name, **kwargs)
    with closing(sqlite3.connect(temporary)) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS vectors "
            "(id TEXT PRIMARY KEY, data BLOB NOT NULL)"
        )
        db.execute("DELETE FROM vectors")
        rows = db.execute(
            "SELECT id,section,text FROM chunks ORDER BY chapter_id,section_id,id"
        ).fetchall()
        documents = [f"{section}\n{text[:1600]}" for _, section, text in rows]
        vectors = model.embed(documents, batch_size=32)
        for (chunk_id, _, _), vector in zip(rows, vectors):
            db.execute(
                "INSERT INTO vectors VALUES (?,?)",
                (chunk_id, array("f", vector).tobytes()),
            )
        db.execute(
            "INSERT OR REPLACE INTO metadata VALUES ('embedding_model',?)",
            (model_name,),
        )
        db.execute(
            "INSERT OR REPLACE INTO metadata VALUES ('shadow_source_sha256',?)",
            (hashlib.sha256(source.read_bytes()).hexdigest(),),
        )
        db.commit()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary.replace(target)
    return {
        "source": str(source),
        "target": str(target),
        "model": model_name,
        "vectors": len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--cache-dir")
    args = parser.parse_args()
    print(json.dumps(
        build(args.source, args.target, args.model, args.cache_dir),
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
