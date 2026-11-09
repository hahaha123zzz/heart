"""同一学生的回合和原生记忆编辑共享锁，避免在途回答恢复已修改记忆。"""
import hashlib
from threading import Lock

_turn_locks = [Lock() for _ in range(64)]


def student_turn_lock(student_id):
    index = int.from_bytes(hashlib.sha256(student_id.encode()).digest()[:2], 'big') % len(_turn_locks)
    return _turn_locks[index]
