"""宿主适配只依赖模块路径与接口，不要求与上游快照哈希一致。"""
import sys
import types

from integrations.deeptutor import learning_binding_adapter


def _fake_binding(tmp_path, monkeypatch):
    root = tmp_path / "vendor"
    source = root / "deeptutor/capabilities/mastery/binding.py"
    source.parent.mkdir(parents=True)
    source.write_text("# source\n", encoding="utf-8")
    (root / "UPSTREAM_SNAPSHOT.json").write_text(
        '{"files":{},"local_changes":[]}', encoding="utf-8")
    binding = types.ModuleType("deeptutor.capabilities.mastery.binding")
    binding.__file__ = str(source)

    async def rebind(**kwargs):
        return None

    async def leave(**kwargs):
        return None
    rebind.__module__ = leave.__module__ = binding.__name__
    binding.rebind_active_path = rebind
    binding.leave_active_path = leave
    mastery = types.ModuleType("deeptutor.capabilities.mastery")
    mastery.binding = binding
    monkeypatch.setitem(sys.modules, "deeptutor", types.ModuleType("deeptutor"))
    monkeypatch.setitem(sys.modules, "deeptutor.capabilities", types.ModuleType("deeptutor.capabilities"))
    monkeypatch.setitem(sys.modules, "deeptutor.capabilities.mastery", mastery)
    monkeypatch.setitem(sys.modules, "deeptutor.capabilities.mastery.binding", binding)
    monkeypatch.setattr("integrations.deeptutor.worker.VENDOR_ROOT", root)
    return binding


def test_binding_adapter_installs_when_upstream_pin_is_empty(tmp_path, monkeypatch):
    binding = _fake_binding(tmp_path, monkeypatch)
    for name in ("rebind_active_path", "leave_active_path"):
        assert not getattr(getattr(binding, name), "_heart_scoped_binding", False)
    learning_binding_adapter.install_learning_binding_adapter()
    for name in ("rebind_active_path", "leave_active_path"):
        assert getattr(binding, name)._heart_scoped_binding is True
