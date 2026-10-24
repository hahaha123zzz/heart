"""用 --database-url 显式选择迁移库；正式库先做一致性备份。"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from database.session_plan_migration import migrate_session_plan

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database-url', required=True)
    args = parser.parse_args()
    engine = create_engine(args.database_url)
    try:
        assert migrate_session_plan(engine)
        print('session_plan schema ready')
    finally:
        engine.dispose()
