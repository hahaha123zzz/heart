"""固定 SDK 的 Windows sidecar URI 兼容适配。"""
from pathlib import Path
from urllib.parse import quote
import os

def sidecar_uri_for(directory):
    path=Path(directory).resolve(strict=True)
    # 1.5.7 的 resolver 只读取 urlsplit(...).path；不能把盘符写入 netloc。
    return ("file:"+quote(path.as_posix(),safe="/:")+"/") if os.name=="nt" else path.as_uri()+"/"
