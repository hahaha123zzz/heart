"""服务器维护的技能映射；题面、规则和版本不匹配时不投影能力。"""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MAP_PATH=ROOT/'exercises/skill_map.json'


def mapping_version():
    return hashlib.sha256(MAP_PATH.read_bytes()).hexdigest()


def question_version(raw_version):
    return hashlib.sha256((raw_version+(ROOT/'exercises/answer_keys.json').read_text(encoding='utf8')+
        (ROOT/'exercise_rubrics.py').read_text(encoding='utf8')+
        (ROOT/'exercise_graders.py').read_text(encoding='utf8')+(ROOT/'symbolic_answers.py').read_text(encoding='utf8')+MAP_PATH.read_text(encoding='utf8')).encode()).hexdigest()


def fingerprint(question, part, key):
    body={'question_text':question['text'],'part':part,'key':key}
    return hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def resolve_mapping(question_id, part_id, version):
    from practice_api import catalog, keys
    data=catalog()
    if version != data['version'] or version != question_version(data['_catalog_source_version']):
        return None
    question=data['by_id'].get(question_id)
    key=keys().get(question_id,{}).get(part_id)
    if not question or not key:
        return None
    part=next((p for p in question['parts'] if p['id']==part_id),None)
    record=json.loads(MAP_PATH.read_text(encoding='utf8'))['items'].get(question_id+':'+part_id)
    if not record or not part or record['fingerprint'] != fingerprint(question,part,key):
        return None
    return dict(record,mapping_version=mapping_version(),source_point=question["knowledge_point"]),part,key
