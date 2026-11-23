"""学习账号仅开放准确匹配的附件读取路由。"""
from deeptutor.api.routers.auth import _learning_surface_for_path


def test_attachment_read_surface_does_not_open_other_file_operations():
    route = "/files/attachments/{session_id}/{attachment_id}/{filename:path}"
    assert _learning_surface_for_path("/files/attachments/s/a/shot.png", "GET", route_path=route) == "chat"
    assert _learning_surface_for_path("/files/attachments/s/a/shot.png", "POST", route_path=route) == ""
    assert _learning_surface_for_path("/files/attachments/admin/export", "GET", route_path="/files/attachments/admin/export") == ""
    assert _learning_surface_for_path("/files/outputs/private", "GET", route_path="/files/outputs/{path:path}") == ""
