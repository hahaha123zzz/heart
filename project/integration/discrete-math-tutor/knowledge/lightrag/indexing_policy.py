"""沿用上游策略身份算法，权威配置来自本项目。"""
import hashlib,json
from urllib.parse import urlsplit,urlunsplit
class IndexingPolicyError(RuntimeError): pass
class EmbeddingMismatchError(IndexingPolicyError): pass
class IndexingModelChangedError(IndexingPolicyError): pass

def _endpoint_identity(value):
    parsed=urlsplit(value or "")
    host=parsed.hostname or ""
    if parsed.port is not None: host=f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(),host.lower(),parsed.path.rstrip("/"),"",""))

def _fingerprint(identity):
    return hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def cache_identity_for_config(config): return _fingerprint(config.identity)
def cache_identity(snapshot): return cache_identity_for_config(snapshot.config)
