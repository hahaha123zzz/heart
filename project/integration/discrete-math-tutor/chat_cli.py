"""使用正式账号经 HTTP API 测试助教；不会创建或清理临时学生。"""

from __future__ import annotations

import getpass
import json
import os
import urllib.error
import urllib.request
from http.cookiejar import CookieJar


def main() -> None:
    base = os.getenv("TUTOR_API_URL", "http://127.0.0.1:8000").rstrip("/")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    csrf = ""

    def post(path: str, data: dict) -> dict:
        headers = {"Content-Type": "application/json", "Origin": base}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = urllib.request.Request(base + path, json.dumps(data, ensure_ascii=False).encode("utf-8"), headers)
        try:
            with opener.open(request, timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                detail = json.load(exc).get("detail", str(exc))
            except (ValueError, OSError):
                detail = str(exc)
            raise RuntimeError(detail) from exc

    print("请先启动 3-start-api.bat。输入已有账号；新账号可在网页注册。")
    username = input("用户名：").strip()
    password = getpass.getpass("密码：")
    session = post("/api/auth/login", {"username": username, "password": password})
    csrf = session["csrf_token"]
    print("已登录。输入 exit 退出。")
    try:
        while True:
            message = input("你> ").strip()
            if message.lower() in ("exit", "quit"):
                break
            if not message:
                continue
            try:
                result = post("/api/chat", {"message": message})
                print("助教> " + result["reply"] + "\n")
            except RuntimeError as exc:
                print("请求失败：" + str(exc))
    finally:
        try:
            post("/api/auth/logout", {})
        except RuntimeError:
            pass


if __name__ == "__main__":
    main()
