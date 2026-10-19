"""Q4 tool foundation against the Q3 synchronous tool contract."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ.setdefault("Q4_ALLOW_PROTOCOL_FALLBACK", "1")

from agents.tools.dispatch import Q3DispatchUnavailable, dispatch_tool_calls
from agents.tools.extensions import (
    EXTENSIONS,
    ExtensionFlags,
    active_extensions,
    owned_tools_for,
)
from agents.tools.loader import DeferredToolLoader, render_deferred_tools_manifest
from agents.tools.local_specs import TOOL_ALIASES
from agents.tools.mounting import (
    ToolMountFlags,
    compose_enabled_tools,
    compose_for_scene,
    default_optional_tools,
)
from agents.tools.protocol import (
    PROTOCOL_SOURCE,
    BaseTool,
    ToolContext,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)
from agents.tools.registry import (
    AuthorizationProxy,
    ScopedToolRegistry,
    ToolRegistry,
    ToolSpec,
)
from agents.tools.scope import Allowlist, ToolGrant, ToolScope
from agents.tools.validation import (
    normalize_arguments,
    parse_arguments,
    validate_arguments,
)


class FakeTool(BaseTool):
    def __init__(
        self,
        name: str,
        *,
        scopes: tuple[str, ...] = (),
        deferred: bool = False,
        description: str = "",
        handler=None,
    ) -> None:
        self.definition = ToolDefinition(
            name=name,
            description=description or f"Fake tool {name}",
            parameters=(ToolParameter(name="value", type="string", required=False),),
        )
        self.scopes = scopes
        self.deferred = deferred
        self._handler = handler
        self.calls: list[dict[str, Any]] = []

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        self.calls.append(dict(arguments))
        if self._handler is not None:
            return self._handler(arguments, context)
        return ToolResult(content=f"{self.definition.name}:{arguments.get('value', '')}")


class FakeEntry:
    def __init__(self, tool: Any) -> None:
        self._tool = tool
        self.name = getattr(tool, "definition", None).name if hasattr(tool, "definition") else "entry"

    def load(self) -> Any:
        return self._tool


def context_for(
    *,
    workspace_root: Path | None = None,
    skills_root: Path | None = None,
    deferred_loader: DeferredToolLoader | None = None,
) -> ToolContext:
    state: dict[str, Any] = {}
    if workspace_root is not None:
        state["workspace_root"] = str(workspace_root)
    if skills_root is not None:
        state["skills_root"] = str(skills_root)
    if deferred_loader is not None:
        state["deferred_loader"] = deferred_loader
    return ToolContext(
        student_id="student-q4",
        session_id="session-q4",
        task_id="task-q4",
        request_id="request-q4",
        state=state,
    )


def scope_for(
    *tools: str,
    scopes: tuple[str, ...] = (),
    workspace_root: Path | None = None,
    skills_root: Path | None = None,
) -> ToolScope:
    return ToolScope(
        student_id="student-q4",
        session_id="session-q4",
        request_id="request-q4",
        grant=ToolGrant(
            tools=Allowlist.of(set(tools)) if tools else Allowlist.unrestricted(),
            scopes=frozenset(scopes),
            workspace_root=workspace_root,
            skills_root=skills_root,
        ),
    )


def view_for(
    base: ToolRegistry,
    *names: str,
    scopes: tuple[str, ...] = (),
    granted: tuple[str, ...] = (),
) -> ScopedToolRegistry:
    allowed = set(names) | set(granted)
    return ScopedToolRegistry(
        base=base,
        selected=names if names else None,
        grant=ToolGrant(
            tools=Allowlist.of(allowed) if allowed else Allowlist.unrestricted(),
            scopes=frozenset(scopes),
        ),
    )


class ProtocolTests(unittest.TestCase):
    def test_uses_q3_protocol_when_present_or_contract_fallback(self):
        self.assertIn(PROTOCOL_SOURCE, {"q3", "q4-contract-fallback"})
        definition = ToolDefinition(
            name="demo",
            description="Demo",
            parameters=(ToolParameter(name="query", type="string"),),
        )
        self.assertEqual(definition.to_openai_schema()["function"]["name"], "demo")

    def test_openai_schema_and_array_items_fallback(self):
        definition = ToolDefinition(
            name="demo",
            description="Demo",
            parameters=(
                ToolParameter(name="query", type="string"),
                ToolParameter(name="tags", type="array", required=False),
                ToolParameter(name="mode", type="string", enum=["a", "b"]),
            ),
        )
        schema = definition.to_openai_schema()
        params = schema["function"]["parameters"]
        self.assertEqual(params["required"], ["query", "mode"])
        self.assertEqual(params["properties"]["tags"]["items"], {"type": "string"})
        self.assertEqual(params["properties"]["mode"]["enum"], ["a", "b"])

    def test_raw_parameters_take_precedence(self):
        definition = ToolDefinition(
            name="raw",
            description="Raw",
            raw_parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        )
        schema = definition.to_openai_schema()
        self.assertFalse(schema["function"]["parameters"]["additionalProperties"])


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.definition = ToolDefinition(
            name="demo",
            description="Demo",
            parameters=(
                ToolParameter(name="count", type="integer"),
                ToolParameter(name="mode", type="string", enum=["read", "write"]),
                ToolParameter(name="enabled", type="boolean", required=False),
                ToolParameter(name="note", type="string", required=False),
            ),
        )

    def test_required_blank_type_enum_and_unknown(self):
        result = validate_arguments(
            self.definition,
            {"count": "3", "mode": "delete", "enabled": "true", "note": " ", "extra": 1},
            allow_unknown=False,
        )
        self.assertFalse(result.ok)
        codes = {issue.code for issue in result.issues}
        self.assertIn("invalid_enum", codes)
        self.assertIn("unknown_argument", codes)
        self.assertNotIn("missing_required", codes)
        self.assertNotIn("type_mismatch", codes)
        self.assertEqual(result.arguments["count"], 3)
        self.assertTrue(result.arguments["enabled"])

    def test_missing_required_and_bad_type(self):
        result = validate_arguments(self.definition, {"count": "x"})
        self.assertFalse(result.ok)
        codes = {issue.code for issue in result.issues}
        self.assertIn("missing_required", codes)
        self.assertIn("type_mismatch", codes)
        self.assertIn("tool call not dispatched", result.message)

    def test_parse_arguments_rejects_non_object(self):
        with self.assertRaises(ValueError):
            parse_arguments("[1, 2]")
        with self.assertRaises(ValueError):
            parse_arguments("{")
        self.assertEqual(parse_arguments('{"a": 1}'), {"a": 1})

    def test_normalize_does_not_mutate_input(self):
        original = {"count": "5", "enabled": "false"}
        normalized = normalize_arguments(self.definition, original)
        self.assertEqual(original, {"count": "5", "enabled": "false"})
        self.assertEqual(normalized, {"count": 5, "enabled": False})


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry(aliases=TOOL_ALIASES)
        self.registry.load_builtins()
        self.context = context_for()

    def test_local_specs_are_lazy_and_listed(self):
        self.assertEqual(self.registry._tools, {})
        self.assertIn("workspace_read", self.registry.names())
        tool = self.registry.get("workspace_read")
        self.assertEqual(tool.definition.name, "workspace_read")
        self.assertEqual(self.registry._tools["workspace_read"], tool)

    def test_q3_registry_surface(self):
        self.assertIn("workspace_list", self.registry.names())
        definitions = self.registry.definitions(["workspace_list"])
        self.assertEqual(definitions[0].name, "workspace_list")
        schema = self.registry.schemas(["workspace_read"])[0]
        self.assertEqual(schema["function"]["name"], "workspace_read")
        self.assertEqual(
            ToolRegistry.canonical_arguments({"b": 1, "a": 2}), '{"a":2,"b":1}'
        )

    def test_alias_resolution_and_defaults(self):
        self.registry.register(FakeTool("echo"))
        self.registry._aliases["demo"] = ("echo", {"value": "default"})
        self.assertEqual(self.registry.resolve_request("demo"), ("echo", {"value": "default"}))
        self.assertEqual(
            self.registry.resolve_request("demo", {"value": "given"}),
            ("echo", {"value": "given"}),
        )
        result = self.registry.run("demo", {}, self.context)
        self.assertEqual(result.content, "echo:default")

    def test_unknown_alias_does_not_fabricate_tool(self):
        self.assertIsNone(self.registry.get("pdf"))
        self.assertNotIn("read_source", self.registry.names())

    def test_duplicate_registration_is_rejected_unless_replace(self):
        tool = FakeTool("echo")
        self.registry.register(tool)
        with self.assertRaises(ValueError):
            self.registry.register(FakeTool("echo"))
        replacement = FakeTool("echo", description="replacement")
        self.registry.register(replacement, replace=True)
        self.assertEqual(self.registry.get("echo").definition.description, "replacement")

    def test_plugin_loading_skips_shadowing_and_loads_new(self):
        self.registry.register(FakeTool("echo"))
        loaded = self.registry.load_plugins(
            entries=[FakeEntry(FakeTool("echo")), FakeEntry(FakeTool("plugin_tool"))]
        )
        self.assertEqual(loaded, ["plugin_tool"])
        self.assertIsNotNone(self.registry.get("plugin_tool"))

    def test_spec_class_path_drift_is_rejected(self):
        spec = ToolSpec.from_class_path(
            "not_the_real_name", "agents.tools.workspace_tools:WorkspaceListTool"
        )
        with self.assertRaises(RuntimeError):
            spec.create()

    def test_run_unknown_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.registry.run("missing", {}, self.context)


class DeferredLoaderTests(unittest.TestCase):
    def test_manifest_and_load_append_live_schema(self):
        registry = ToolRegistry()
        deferred = FakeTool(
            "mcp_demo", deferred=True, description="External\nprovider tool"
        )
        registry.register(deferred)
        registry.register(FakeTool("visible"))
        persisted: list[tuple[str, set[str]]] = []
        loader = DeferredToolLoader(
            registry=registry,
            session_id="s1",
            loaded={"stale"},
            persist=lambda session, names: persisted.append((session, names)),
        )
        live: list[dict[str, Any]] = []
        loader.bind_live_schemas(live)
        manifest = render_deferred_tools_manifest(registry.deferred_tools(), language="zh")
        self.assertIn("扩展工具", manifest)
        self.assertIn("mcp_demo", manifest)
        self.assertIn("External provider tool", manifest)

        outcome = loader.load(["mcp_demo", "mcp_demo", "unknown"])
        self.assertEqual(outcome["loaded"], ["mcp_demo"])
        self.assertEqual(outcome["unknown"], ["unknown"])
        self.assertEqual(len(live), 1)
        self.assertEqual(persisted[-1][0], "s1")
        self.assertEqual(loader.load(["mcp_demo"])["already_loaded"], ["mcp_demo"])
        self.assertEqual(loader.initial_schemas()[0]["function"]["name"], "mcp_demo")

    def test_allowed_set_limits_loading(self):
        registry = ToolRegistry()
        registry.register(FakeTool("a", deferred=True))
        registry.register(FakeTool("b", deferred=True))
        loader = DeferredToolLoader(registry=registry, allowed={"a"})
        self.assertEqual(loader.load(["a", "b"])["unknown"], ["b"])


class ScopeTests(unittest.TestCase):
    def test_grant_narrow_and_allowlist_semantics(self):
        wider = ToolGrant(
            tools=Allowlist.unrestricted(),
            scopes=frozenset({"workspace:read", "skills:read"}),
        )
        restricted = ToolGrant(
            tools=Allowlist.of({"a"}),
            scopes=frozenset({"workspace:read"}),
        )
        narrowed = wider.narrow(restricted)
        self.assertEqual(narrowed.tools.names, frozenset({"a"}))
        self.assertEqual(narrowed.scopes, frozenset({"workspace:read"}))
        self.assertTrue(narrowed.allows_scope("workspace:read"))
        self.assertFalse(narrowed.allows_scope("skills:read"))
        self.assertFalse(ToolGrant().allows_tool("anything"))
        self.assertTrue(ToolGrant(tools=Allowlist.unrestricted()).allows_tool("anything"))
        self.assertFalse(ToolGrant().allows_scope("workspace:read"))

    def test_default_grant_is_deny_by_default(self):
        base = ToolRegistry()
        base.register(FakeTool("anything"))
        view = ScopedToolRegistry(base=base)
        self.assertEqual(view.names(), [])
        self.assertFalse(view.run("anything", {}, context_for()).success)

    def test_scoped_registry_refuses_unauthorized_and_missing_scope(self):
        base = ToolRegistry()
        base.register(FakeTool("allowed", scopes=("workspace:read",)))
        base.register(FakeTool("denied"))
        base.register(FakeTool("scoped", scopes=("workspace:write",)))
        view = ScopedToolRegistry(
            base=base,
            grant=ToolGrant(
                tools=Allowlist.of({"allowed", "scoped"}),
                scopes=frozenset({"workspace:read"}),
            ),
        )
        self.assertEqual(view.names(), ["allowed"])
        denied = view.run("denied", {}, context_for())
        self.assertFalse(denied.success)
        self.assertEqual(denied.metadata["error"], "unauthorized_tool")
        proxy = AuthorizationProxy(
            base.get("scoped"),
            ToolGrant(tools=Allowlist.of({"scoped"}), scopes=frozenset({"workspace:read"})),
        )
        missing = proxy.run({}, context_for())
        self.assertFalse(missing.success)
        self.assertEqual(missing.metadata["error"], "missing_scope")

    def test_scoped_registry_overlay_collision_is_dropped(self):
        base = ToolRegistry()
        base.register(FakeTool("shared"))
        view = ScopedToolRegistry(
            base=base,
            overlay=[FakeTool("shared"), FakeTool("own")],
            grant=ToolGrant(tools=Allowlist.unrestricted()),
        )
        self.assertEqual(view.names(), ["shared", "own"])

    def test_authorization_proxy_enforces_argument_validation(self):
        class TypedTool(BaseTool):
            definition = ToolDefinition(
                name="typed",
                description="typed",
                parameters=(ToolParameter(name="count", type="integer"),),
            )

            def run(self, arguments, context):
                return ToolResult(content=str(arguments["count"]))

        proxy = AuthorizationProxy(
            TypedTool(), ToolGrant(tools=Allowlist.of({"typed"}))
        )
        invalid = proxy.run({"count": "not-a-number"}, context_for())
        self.assertFalse(invalid.success)
        self.assertEqual(invalid.metadata["error"], "invalid_arguments")
        unknown = proxy.run({"count": 3, "extra": 1}, context_for())
        self.assertFalse(unknown.success)
        self.assertEqual(unknown.metadata["error"], "invalid_arguments")
        valid = proxy.run({"count": "3"}, context_for())
        self.assertTrue(valid.success)
        self.assertEqual(valid.content, "3")

    def test_alias_defaults_are_applied_in_scoped_view(self):
        base = ToolRegistry(aliases={"demo": ("echo", {"value": "default"})})
        base.register(FakeTool("echo"))
        view = ScopedToolRegistry(
            base=base,
            grant=ToolGrant(tools=Allowlist.of({"echo"})),
        )
        result = view.run("demo", {}, context_for())
        self.assertTrue(result.success)
        self.assertEqual(result.content, "echo:default")

    def test_authorization_proxy_rejects_state_root_mismatch(self):
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as other:
            tool = FakeTool("scoped", scopes=("workspace:read",))
            proxy = AuthorizationProxy(
                tool,
                ToolGrant(
                    tools=Allowlist.of({"scoped"}),
                    scopes=frozenset({"workspace:read"}),
                    workspace_root=Path(allowed),
                ),
            )
            mismatch = proxy.run({}, context_for(workspace_root=Path(other)))
            self.assertFalse(mismatch.success)
            self.assertEqual(mismatch.metadata["error"], "root_mismatch")
            matched = proxy.run({}, context_for(workspace_root=Path(allowed)))
            self.assertTrue(matched.success)

    def test_mount_tool_rejects_collision_substitution(self):
        base = ToolRegistry()
        protected = FakeTool("protected")
        base.register(protected)
        view = ScopedToolRegistry(
            base=base,
            grant=ToolGrant(tools=Allowlist.unrestricted()),
        )
        self.assertFalse(view.mount_tool(FakeTool("protected", deferred=True)))

    def test_mount_tool_allows_deferred_but_not_unselected_plain(self):
        base = ToolRegistry()
        plain = FakeTool("plain")
        deferred = FakeTool("deferred", deferred=True)
        base.register(plain)
        base.register(deferred)
        view = ScopedToolRegistry(
            base=base,
            selected=set(),
            grant=ToolGrant(tools=Allowlist.of({"plain", "deferred"})),
        )
        self.assertFalse(view.mount_tool(plain))
        self.assertTrue(view.mount_tool(deferred))
        self.assertEqual(view.names(), ["deferred"])


class ExtensionTests(unittest.TestCase):
    def test_catalog_has_all_14_unique_names(self):
        names = [extension.name for extension in EXTENSIONS]
        self.assertEqual(len(names), 14)
        self.assertEqual(len(set(names)), 14)

    def test_each_activation_gate_is_trusted_context_only(self):
        cases = [
            ("ask_questions_mode", "ask_questions"),
            ("mastery_mode", "mastery"),
            ("solve_mode", "solve"),
            ("has_obsidian_vault", "obsidian"),
            ("has_marginnote", "marginnote4"),
            ("has_subagent", "subagent"),
            ("has_ima", "ima"),
            ("reading_open", "immersive_reading"),
            ("has_source_index", "explore_context"),
            ("setup_mode", "setup"),
            ("partner_authoring_mode", "partner_authoring"),
            ("partner_group", "partner_group"),
            ("visualization_generation", "visualization_generation"),
        ]
        for flag, expected in cases:
            flags = ExtensionFlags(**{flag: True})
            self.assertEqual([item.name for item in active_extensions(flags)], [expected])
        self.assertEqual(
            [
                item.name
                for item in active_extensions(
                    ExtensionFlags(course_id="course-1"), "course_study"
                )
            ],
            ["course_study"],
        )
        self.assertEqual(
            [item.name for item in active_extensions(ExtensionFlags(), "course_study")],
            [],
        )
        self.assertEqual(
            [
                item.name
                for item in active_extensions(
                    ExtensionFlags(course_id="course-1"), "chat"
                )
            ],
            [],
        )
        self.assertEqual(
            [item.name for item in active_extensions(ExtensionFlags(), "deep_solve")],
            ["solve"],
        )

    def test_owned_tools_are_deduplicated(self):
        active = active_extensions(ExtensionFlags(mastery_mode=True, solve_mode=True))
        tools = owned_tools_for(active)
        self.assertIn("mastery_quiz", tools)
        self.assertIn("solve_plan", tools)
        self.assertEqual(len(tools), len(set(tools)))


class MountingTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        for name in (
            "workspace_list",
            "workspace_read",
            "workspace_search",
            "rag",
            "exec",
            "obsidian_search",
            "ask_user",
            "read_skill",
            "load_tools",
            "mastery_quiz",
        ):
            self.registry.register(FakeTool(name))

    def test_conditional_and_baseline_mounts(self):
        base = compose_enabled_tools(registry=self.registry, mount_flags=ToolMountFlags())
        self.assertIn("workspace_list", base)
        self.assertNotIn("rag", base)
        self.assertNotIn("exec", base)
        with_context = compose_enabled_tools(
            registry=self.registry,
            mount_flags=ToolMountFlags(has_kb=True, has_exec=True, has_skills=True),
        )
        self.assertIn("rag", with_context)
        self.assertIn("exec", with_context)
        self.assertIn("read_skill", with_context)

    def test_extensions_do_not_leak_without_activation(self):
        chat = compose_for_scene(scene="chat", registry=self.registry)
        self.assertNotIn("obsidian_search", chat)
        self.assertNotIn("mastery_quiz", chat)
        mastery = compose_for_scene(
            scene="mastery_path",
            registry=self.registry,
            mount_flags=ToolMountFlags(
                extension_flags=ExtensionFlags(mastery_mode=True)
            ),
        )
        self.assertIn("mastery_quiz", mastery)
        obsidian = compose_for_scene(
            scene="chat",
            registry=self.registry,
            mount_flags=ToolMountFlags(
                extension_flags=ExtensionFlags(has_obsidian_vault=True)
            ),
        )
        self.assertIn("obsidian_search", obsidian)

    def test_user_toggle_whitelist_and_defaults(self):
        requested = compose_enabled_tools(
            registry=self.registry, requested_tools=["rag"], optional_whitelist=[]
        )
        self.assertNotIn("rag", requested)
        self.assertNotIn("exec", default_optional_tools())


class WorkspaceToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "notes").mkdir()
        (self.root / "notes" / "a.txt").write_text("alpha 自变量\nbeta\n", encoding="utf-8")
        (self.root / "README.md").write_text("outside notes\n", encoding="utf-8")
        (self.root / "secret.bin").write_bytes(b"\xff\xfe\x00")
        self.registry = ToolRegistry()
        self.registry.load_builtins()
        self.view = view_for(
            self.registry,
            "workspace_list",
            "workspace_read",
            "workspace_search",
            scopes=("workspace:read",),
        )
        self.context = context_for(workspace_root=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def call(self, name, arguments):
        return self.view.run(name, arguments, self.context)

    def test_list_read_search(self):
        listed = self.call("workspace_list", {"depth": 2})
        self.assertTrue(listed.success)
        self.assertIn("notes/a.txt", listed.content)
        read = self.call("workspace_read", {"path": "notes/a.txt", "limit": 5})
        self.assertEqual(read.content, "alpha")
        self.assertTrue(read.metadata["truncated"])
        search = self.call("workspace_search", {"query": "自变量"})
        self.assertTrue(search.success)
        self.assertIn("notes/a.txt", search.content)
        self.assertIn('"line": 1', search.content)

    def test_path_traversal_and_absolute_are_refused(self):
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, "x.txt").write_text("secret", encoding="utf-8")
            for path in ("../x.txt", str(Path(outside, "x.txt"))):
                result = self.call("workspace_read", {"path": path})
                self.assertFalse(result.success, path)
                self.assertEqual(result.metadata["error"], "workspace_access")

    def test_missing_workspace_binding_fails_closed(self):
        result = self.view.run("workspace_list", {}, context_for())
        self.assertFalse(result.success)
        self.assertIn("No active workspace", result.content)

    def test_binary_file_is_refused(self):
        result = self.call("workspace_read", {"path": "secret.bin"})
        self.assertFalse(result.success)

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_windows_junction_cannot_escape_or_loop(self):
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, "secret.txt").write_text("OUTSIDE_SECRET_TOKEN", encoding="utf-8")
            link = self.root / "junction"
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), outside],
                capture_output=True,
            )
            if result.returncode != 0:
                self.skipTest("could not create a Windows junction")
            cycle = self.root / "loop"
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(cycle), str(self.root)],
                capture_output=True,
            )

            listing = self.call("workspace_list", {"depth": 5})
            self.assertTrue(listing.success)
            self.assertNotIn("junction", listing.content)
            self.assertNotIn("loop/loop", listing.content)

            search = self.call("workspace_search", {"query": "OUTSIDE_SECRET_TOKEN"})
            self.assertTrue(search.success)
            self.assertEqual(search.metadata["count"], 0)

            read = self.call("workspace_read", {"path": "junction/secret.txt"})
            self.assertFalse(read.success)


class SkillAndLoaderToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        skill = self.root / "demo-skill"
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Demo\nFollow these steps.", encoding="utf-8")
        (skill / "references" / "api.md").write_text("API reference", encoding="utf-8")
        self.registry = ToolRegistry()
        self.registry.load_builtins()
        self.registry.register(FakeTool("mcp_demo", deferred=True))
        self.view = view_for(
            self.registry,
            "read_skill",
            "load_tools",
            scopes=("skills:read", "tools:load"),
            granted=("mcp_demo",),
        )
        self.live: list[dict[str, Any]] = []
        self.loader = DeferredToolLoader(
            registry=self.registry,
            session_id="s",
            on_loaded=self.view.mount_tool,
        )
        self.loader.bind_live_schemas(self.live)
        self.context = context_for(
            skills_root=self.root,
            deferred_loader=self.loader,
        )

    def tearDown(self):
        self.temp.cleanup()

    def call(self, name, arguments):
        return self.view.run(name, arguments, self.context)

    def test_read_skill_and_reference(self):
        result = self.call("read_skill", {"name": "demo-skill"})
        self.assertTrue(result.success)
        self.assertIn("Follow these steps", result.content)
        reference = self.call(
            "read_skill", {"name": "demo-skill", "file": "references/api.md"}
        )
        self.assertEqual(reference.content, "API reference")

    def test_read_skill_blocks_traversal_and_unknown(self):
        traversal = self.call(
            "read_skill", {"name": "demo-skill", "file": "../outside.txt"}
        )
        self.assertFalse(traversal.success)
        unknown = self.call("read_skill", {"name": "missing"})
        self.assertFalse(unknown.success)
        self.assertIn("Available skills", unknown.content)

    def test_reads_real_project_skill_library(self):
        project_skills = Path(__file__).resolve().parents[1] / "visualization/skills"
        if not (project_skills / "finite-structures" / "SKILL.md").is_file():
            self.skipTest("project skill library is unavailable")
        context = context_for(skills_root=project_skills)
        result = self.view.run(
            "read_skill", {"name": "finite-structures"}, context
        )
        self.assertTrue(result.success)
        self.assertIn("有限集合", result.content)

    def test_persisted_loader_mounts_before_advertising_schema(self):
        view = view_for(
            self.registry,
            "read_skill",
            "load_tools",
            scopes=("skills:read", "tools:load"),
            granted=("mcp_demo",),
        )
        loader = DeferredToolLoader(
            registry=self.registry,
            loaded={"mcp_demo"},
            on_loaded=view.mount_tool,
        )
        schemas = loader.initial_schemas()
        self.assertEqual([row["function"]["name"] for row in schemas], ["mcp_demo"])
        self.assertIsNotNone(view.get("mcp_demo"))

        denied_view = view_for(
            self.registry,
            "read_skill",
            "load_tools",
            scopes=("skills:read", "tools:load"),
        )
        denied = DeferredToolLoader(
            registry=self.registry,
            loaded={"mcp_demo"},
            on_loaded=denied_view.mount_tool,
        )
        self.assertEqual(denied.initial_schemas(), [])
        self.assertIsNone(denied_view.get("mcp_demo"))

    def test_load_tools_mounts_schema_and_tool_same_turn(self):
        result = self.call("load_tools", {"names": ["mcp_demo"]})
        self.assertTrue(result.success)
        self.assertEqual(len(self.live), 1)
        self.assertEqual(self.live[0]["function"]["name"], "mcp_demo")
        self.assertIsNotNone(self.view.get("mcp_demo"))
        self.assertIn(
            "mcp_demo", [item["function"]["name"] for item in self.view.schemas()]
        )
        called = self.view.run("mcp_demo", {"value": "now"}, self.context)
        self.assertTrue(called.success)
        self.assertEqual(called.content, "mcp_demo:now")
        again = self.call("load_tools", {"names": ["mcp_demo"]})
        self.assertIn("Already loaded", again.content)


@unittest.skipUnless(
    importlib.util.find_spec("agents.tool_protocol") is not None,
    "Q3 tool protocol is not merged in this checkout",
)
class Q3ActualProtocolTests(unittest.TestCase):
    def test_q3_protocol_is_the_active_one(self):
        self.assertEqual(PROTOCOL_SOURCE, "q3")
        self.assertEqual(BaseTool.__module__, "agents.tool_protocol")


class Q3BridgeTests(unittest.TestCase):
    def test_bridge_reports_missing_q3_dispatcher(self):
        with patch.dict(sys.modules, {"agents.tool_dispatch": None}):
            with self.assertRaises(Q3DispatchUnavailable):
                dispatch_tool_calls(
                    tool_calls=[],
                    registry=view_for(ToolRegistry()),
                    context=context_for(),
                )

    def test_bridge_delegates_to_q3(self):
        module = types.ModuleType("agents.tool_dispatch")
        seen: dict[str, Any] = {}

        def fake_dispatch(**kwargs):
            seen.update(kwargs)
            return "q3-outcome"

        module.dispatch_tool_calls = fake_dispatch
        registry = view_for(ToolRegistry())
        context = context_for()
        with patch.dict(sys.modules, {"agents.tool_dispatch": module}):
            outcome = dispatch_tool_calls(
                tool_calls=[{"id": "1", "name": "x", "arguments": {}}],
                registry=registry,
                context=context,
                max_calls=3,
                timeout_seconds=5,
            )
        self.assertEqual(outcome, "q3-outcome")
        self.assertIs(seen["registry"], registry)
        self.assertIs(seen["context"], context)
        self.assertEqual(seen["max_calls"], 3)
        self.assertEqual(seen["timeout_seconds"], 5)


if __name__ == "__main__":
    unittest.main()
