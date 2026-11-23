"""单个已发布文件的能力签名；身份标识本身不构成下载授权。"""
import hashlib
import hmac
import json
import os
from urllib.parse import urlencode, quote


def signature(student_id, session_id, task_id, item_id):
    token = os.getenv('DEEPTUTOR_BRIDGE_TOKEN', '')
    if len(token) < 32:
        raise ValueError('文件签名凭据未配置')
    body = json.dumps(['heart-artifact-v1',student_id,session_id,task_id,item_id],separators=(',',':')).encode()
    return hmac.new(token.encode(), body, hashlib.sha256).hexdigest()


def verify(student_id, session_id, task_id, item_id, provided):
    expected = signature(student_id,session_id,task_id,item_id)
    return isinstance(provided,str) and len(provided)==64 and hmac.compare_digest(expected,provided)


def url(student_id, session_id, task_id, item_id):
    return '/api/deeptutor/tasks/'+quote(task_id,safe='')+'/artifacts/'+quote(item_id,safe='')+'?'+urlencode({
        'student_id':student_id,'session_id':session_id,
        'signature':signature(student_id,session_id,task_id,item_id)})
