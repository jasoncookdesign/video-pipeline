"""Reference argv assembler for the control-tower schema.

This is the Python *reference implementation* of the process contract (SADD §2.4
"Process"): given a task, the user's form values, and resolved artifact paths,
produce the exact ``argv`` the GUI would run. The Rust process supervisor ports
this; the contract test asserts they agree. Keeping it here means the rule for
"how a form becomes a command" lives next to the schema that defines the form,
and the GUI's resolved-command preview can never silently diverge from a runnable
command.

It is pure (no I/O) and depends only on ``model``.
"""

from __future__ import annotations

from typing import Any

from .model import Schema, Task


def _task(schema: Schema, task_id: str) -> Task:
    for t in schema.tasks:
        if t.id == task_id:
            return t
    raise KeyError(f"no task {task_id!r}")


def _row_scalar(v: Any) -> str:
    """Render a row field value into its ``key=value`` token (bool lowercased)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def resolve_argv(
    schema: Schema,
    task_id: str,
    form_values: dict[str, Any] | None = None,
    artifact_paths: dict[str, str] | None = None,
) -> list[str]:
    """Assemble runnable argv for ``task_id``.

    ``form_values`` maps param key -> value (missing keys fall back to the param
    default). ``artifact_paths`` maps artifact id -> concrete file path (the
    scheduler resolves these from the latest enabled writer / declared path).
    """
    form_values = form_values or {}
    artifact_paths = artifact_paths or {}
    task = _task(schema, task_id)

    argv: list[str] = [schema.engine.cli_entrypoint, *task.subcommand.split()]

    # 1) positionals (params + io), interleaved by `order`
    positionals: list[tuple[int, str]] = []
    for p in task.params:
        if p.arity == "positional":
            val = form_values.get(p.key, p.default)
            if val is None:
                if p.required:
                    raise ValueError(f"{task_id}: required positional {p.key!r} missing")
                continue
            positionals.append((p.order, str(val)))
    for b in task.io:
        if b.via == "positional":
            path = artifact_paths.get(b.artifact)
            if path is None:
                raise ValueError(f"{task_id}: no path for positional artifact {b.artifact!r}")
            positionals.append((b.order, str(path)))
    for _, val in sorted(positionals, key=lambda x: x[0]):
        argv.append(val)

    # 2) value + switch + rows params
    for p in task.params:
        if p.arity == "positional":
            continue
        val = form_values.get(p.key, p.default)
        if p.arity == "switch":
            if val:
                argv.append(p.flag)  # presence-only
        elif p.arity == "rows":
            # Repeatable structured rows: one `flag spec` pair per non-empty row,
            # spec = the row's `key=value;…` over the fields it carries. Identical
            # encoding in command.rs / ipc.ts (the golden-argv contract pins them).
            for row in (val or []):
                if not isinstance(row, dict):
                    continue
                parts = []
                for rf in (p.row or []):
                    v = row.get(rf.key)
                    if v is None or v == "":
                        continue
                    parts.append(f"{rf.key}={_row_scalar(v)}")
                if parts and p.flag:
                    argv.extend([p.flag, ";".join(parts)])
        elif p.arity == "value":
            if val is None:
                if p.required:
                    raise ValueError(f"{task_id}: required param {p.key!r} missing")
                continue
            argv.extend([p.flag, str(val)])

    # 3) io flag bindings (inputs + outputs)
    for b in task.io:
        if b.via == "flag":
            path = artifact_paths.get(b.artifact)
            if path is None:
                raise ValueError(f"{task_id}: no path for artifact {b.artifact!r}")
            argv.extend([b.flag, str(path)])

    return argv
