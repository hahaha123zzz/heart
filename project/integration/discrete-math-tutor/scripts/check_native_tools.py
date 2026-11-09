"""核对 100 个内置工具能否被原生目录真实实例化；不调用工具本身。

在 .venv-deeptutor 中运行：.venv-deeptutor/Scripts/python.exe -X utf8 -B scripts/check_native_tools.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    from deeptutor.tools.builtin_specs import BUILTIN_TOOL_SPECS
    from deeptutor.runtime.registry.tool_registry import ToolRegistry
    from deeptutor.runtime.bootstrap.builtin_capabilities import BUILTIN_CAPABILITY_SPECS
    from deeptutor.runtime.registry.capability_registry import CapabilityRegistry
    from deeptutor.capabilities.registry import BUILTIN_LOOP_CAPABILITY_SPECS

    registry = ToolRegistry()
    registry.load_builtins()
    rows = []
    for spec in BUILTIN_TOOL_SPECS:
        row = {"name": spec.name, "class_path": spec.class_path}
        try:
            tool = spec.create()
            definition = tool.get_definition()
            row.update(loaded=True, defined_name=definition.name,
                       deferred=bool(getattr(tool, "deferred", False)),
                       description=(definition.description or "")[:120])
        except Exception as exc:  # noqa: BLE001 - 记录每项真实原因，不中断整表
            row.update(loaded=False, error=f"{type(exc).__name__}: {exc}"[:300])
        rows.append(row)
    failures = [row for row in rows if not row["loaded"]]
    registry.load_builtins()

    capability_registry = CapabilityRegistry()
    capability_registry.load_builtins()
    capabilities = []
    for name, spec in BUILTIN_CAPABILITY_SPECS.items():
        entry = {"name": name, "class_path": spec.class_path}
        try:
            capability = capability_registry.get(name)
            entry.update(loaded=capability is not None,
                         declared_name=getattr(capability, "name", None),
                         declared_stages=list(getattr(capability, "stages", []) or []))
            entry["name_match"] = entry["declared_name"] == name
            entry["stages_match"] = entry["declared_stages"] == list(spec.manifest.stages)
        except Exception as exc:  # noqa: BLE001 - 单项失败不掩盖其余能力
            entry.update(loaded=False, error=f"{type(exc).__name__}: {exc}"[:300])
        capabilities.append(entry)
    capability_failures = [entry for entry in capabilities
                           if not entry.get("loaded") or not entry.get("name_match") or not entry.get("stages_match")]

    tool_names = {row["name"] for row in rows}
    extensions = []
    for spec in BUILTIN_LOOP_CAPABILITY_SPECS:
        entry = {"name": spec.name, "class_path": spec.class_path}
        try:
            extension = spec.create()
            owned = list(getattr(extension, "owned_tools", ()) or ())
            hooks = {hook: callable(getattr(extension, hook, None)) for hook in
                     ("is_active", "system_block", "augment_kwargs", "pre_loop_seed")}
            entry.update(loaded=True, declared_name=getattr(extension, "name", None), owned_tools=owned,
                         missing_owned_tools=[name for name in owned if name not in tool_names], hooks=hooks)
            entry["ok"] = (entry["declared_name"] == spec.name and not entry["missing_owned_tools"]
                           and hooks["is_active"])
        except Exception as exc:  # noqa: BLE001 - 单项失败不掩盖其余扩展
            entry.update(loaded=False, ok=False, error=f"{type(exc).__name__}: {exc}"[:300])
        extensions.append(entry)
    extension_failures = [entry for entry in extensions if not entry.get("ok")]

    report = {
        "checked": len(rows),
        "loaded": len(rows) - len(failures),
        "failed": len(failures),
        "failures": failures,
        "deferred": sum(1 for row in rows if row.get("deferred")),
        "registry_get_loaded": sum(1 for spec in BUILTIN_TOOL_SPECS if registry.get(spec.name) is not None),
        "capabilities": capabilities,
        "capability_failures": capability_failures,
        "extensions": extensions,
        "extension_failures": extension_failures,
        "tools": rows,
    }
    folder = ROOT / ".runtime/native-tools"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (time.strftime("%Y%m%d-%H%M%S") + ".json")
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("checked", "loaded", "failed", "deferred", "registry_get_loaded")}
                     | {"capabilities": len(capabilities), "capability_failed": len(capability_failures),
                        "extensions": len(extensions), "extension_failed": len(extension_failures)},
                     ensure_ascii=False))
    for row in failures:
        print("FAILED_TOOL", row["name"], row["error"])
    for entry in capability_failures:
        print("FAILED_CAPABILITY", entry["name"], entry.get("error") or
              {"name_match": entry.get("name_match"), "stages_match": entry.get("stages_match")})
    for entry in extension_failures:
        print("FAILED_EXTENSION", entry["name"], entry.get("error") or
              {"missing_owned_tools": entry.get("missing_owned_tools"), "hooks": entry.get("hooks")})
    print("report", target)
    return 0 if not failures and not capability_failures and not extension_failures else 1


if __name__ == "__main__":
    sys.exit(main())
