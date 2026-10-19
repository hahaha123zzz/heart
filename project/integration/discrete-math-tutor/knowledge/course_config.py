"""原项目教材选择，正式教材默认使用实验心理学。"""
import os
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
COURSE_ID=os.getenv('TUTOR_COURSE','experimental-psychology-3')
if COURSE_ID not in ('discrete-math','experimental-psychology-3'):
    raise ValueError('TUTOR_COURSE不属于已导入的教材')
PSYCHOLOGY=COURSE_ID=='experimental-psychology-3'
PSYCHOLOGY_DIR=ROOT/'knowledge/courses/experimental-psychology-3'
COURSE_TITLE='实验心理学' if PSYCHOLOGY else '离散数学'
DEFAULT_GOAL='实验心理学的研究方法' if PSYCHOLOGY else '图的基本概念'

def public_course():
    return {'id':COURSE_ID,'title':COURSE_TITLE,'default_goal':DEFAULT_GOAL,
            'reading_map_url':'/api/course/reading-map',
            'page_label':'生成阅读版第' if PSYCHOLOGY else '原教材第'}
