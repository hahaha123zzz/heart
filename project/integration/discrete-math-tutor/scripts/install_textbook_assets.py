"""显式安装固定教材资产：完整核对教材与活动索引后一次性发布。"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=None)
    parser.add_argument('--textbook', type=Path, default=None)
    parser.add_argument('--candidate', type=Path, default=None)
    args = parser.parse_args()
    from knowledge.course_release import validate
    from knowledge.fixed_book_assets import assets_root, install
    from knowledge.lightrag.course_input import COURSE
    from knowledge.lightrag.retrieval import LightRagBackend

    textbook = (args.textbook or Path(os.environ['TUTOR_PSYCHOLOGY_DIR'])).resolve(strict=True)
    candidate = (args.candidate or Path(os.environ['LIGHTRAG_CANDIDATE_PATH'])).resolve(strict=True)
    release = validate(refresh=True)
    backend = LightRagBackend(candidate, authorized_course_ids={COURSE}, allow_candidate=True,
                              source_root=textbook)
    source_map = backend.load_source_map()
    root = args.assets or assets_root()
    record = install(root, textbook, candidate, release_id=release['release_id'], source_map=source_map)
    print(json.dumps({'assets': str(root), 'release_id': record['release_id'],
                      'textbook_files': len(record['textbook']['files']),
                      'frozen_files': len(record['frozen']['files']),
                      'chapters': len(source_map)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
