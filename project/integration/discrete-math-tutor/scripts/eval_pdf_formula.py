"""用已有正式账号进行 PDF 选区回归；不会创建临时学生。"""

import getpass
import json
import os
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from knowledge.pdf_reader import document

base = os.getenv("TUTOR_API_URL", "http://127.0.0.1:8000").rstrip("/")
username = os.getenv("TUTOR_USERNAME") or input("测试账号用户名：").strip()
password = os.getenv("TUTOR_PASSWORD") or getpass.getpass("密码：")
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def post(path, payload, csrf=""):
    headers = {"Content-Type": "application/json", "Origin": base}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    request = urllib.request.Request(base + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers)
    with client.open(request, timeout=120) as response:
        return json.load(response)


session = post("/api/auth/login", {"username": username, "password": password})
record = document("chapter-03")
selection = {"document_id": record["document_id"], "version": record["version"],
             "kind": "area", "rects": [{"page": 8, "x1": .18, "y1": .12, "x2": .87, "y2": .16}],
             "text": ""}
folder = Path("artifacts/pdf-reader")
folder.mkdir(parents=True, exist_ok=True)
(folder / "formula-selection.json").write_text(json.dumps(selection), encoding="utf-8")
try:
    result = post("/api/chat", {"message": "请解释我圈选的二项式展开公式，为什么每项前面有组合数？",
                                "selection": selection}, session["csrf_token"])
    (folder / "formula-real-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"reply": result["reply"], "quality": result["quality_check"],
                      "refs": result["selection_ref"]["rects"]}, ensure_ascii=False))
finally:
    post("/api/auth/logout", {}, session["csrf_token"])
