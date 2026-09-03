"""Compact ADILang-compatible IR used by the local agent.

This implements the protocol subset needed by this service. The canonical reference
is the user's ADILang project at Proj/1_Local/adilang (v1.18.0).
"""

from __future__ import annotations

import datetime as dt
import re
from collections import OrderedDict
from typing import Any

from .compactor import optimize_src

VERSION = "1.18.0"
MODULE_KEYS = {
    "intent": ("mode", "payload", "verb"),
    "reply": ("mode", "content", "recs", "world"),
    "task": ("assign", "input", "expect"),
    "event": ("source", "key", "session", "at", "line", "token", "guidance"),
    "memory": ("key", "topic", "fact", "confidence", "source", "at"),
    "plan": ("steps", "parallel"),
    "state": (
        "user_key", "session_id", "job_id", "muted", "speaking", "mic_active",
        "quality", "status", "progress", "provider", "elapsed", "at",
    ),
}
REQUIRED = {
    "intent": ("mode", "payload"),
    "reply": ("content",),
    "task": ("assign", "input", "expect"),
    "event": ("source", "at"),
    "memory": ("key", "fact"),
    "plan": ("steps",),
    "state": ("user_key", "at"),
}
VERBS = {"ask", "inform", "command", "greet", "system"}
MODE_ALIASES = {
    "MODE_CONVERSATION": "conv",
    "MODE_CODE_ENGINEERING": "code",
    "MODE_CALCULATION": "calc",
    "MODE_SYSTEM_DIAGNOSTICS": "diag",
    "MODE_TASK_EXECUTION": "task",
    "MODE_AGENT_COLLABORATION": "collab",
    "MODE_CHAT": "chat",
    "MODE_JOB_CAREER": "job",
    "MODE_IMAGE_GENERATION": "image",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def minify(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _q(value: Any) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _mode(value: str) -> str:
    return MODE_ALIASES.get(value, value)


def encode_intent(mode: str, payload: str, verb: str = "ask", compact: bool = False) -> str:
    verb = verb if verb in VERBS else "ask"
    raw = f'intent {_q(verb)}{{mode {_q(_mode(mode))} payload {_q(minify(payload))} verb {_q(verb)}}}'
    return optimize_src(raw) if compact else raw


def encode_reply(mode: str, content: str, recs: list[str] | None = None, compact: bool = False) -> str:
    tail = ""
    if recs:
        tail = " recs[" + " ".join(_q(item) for item in recs) + "]"
    raw = f'reply "answer"{{mode {_q(_mode(mode))} content {_q(minify(content))}{tail}}}'
    return optimize_src(raw) if compact else raw


def encode_task(name: str, assign: str, input_text: str, expect: str, compact: bool = False) -> str:
    raw = f'task {_q(name)}{{assign {_q(assign)} input {_q(minify(input_text))} expect {_q(minify(expect))}}}'
    return optimize_src(raw) if compact else raw


def encode_memory(
    key: str,
    fact: str,
    *,
    topic: str | None = None,
    confidence: float = 1.0,
    source: str = "local",
    at: str | None = None,
    compact: bool = False,
) -> str:
    topic_field = f" topic {_q(topic)}" if topic else ""
    timestamp = at or _now()
    raw = (
        f'memory {_q(key)}{{key {_q(key)} fact {_q(minify(fact))}{topic_field} '
        f'confidence {_q(f"{confidence:.2f}")} source {_q(source)} at {_q(timestamp)}}}'
    )
    return optimize_src(raw) if compact else raw


def encode_memory_chunk(
    chunk_id: str,
    fact: str,
    *,
    source: str = "local",
    topic: str | None = None,
    compact: bool = True,
) -> str:
    """Encode document chunk to ultra-compact ADILang IR representation for AI indexing."""
    return encode_memory(
        key=chunk_id,
        fact=fact,
        topic=topic,
        confidence=1.0,
        source=source,
        compact=compact,
    )


def encode_plan(name: str, steps: list[str], parallel: bool = False, compact: bool = False) -> str:
    encoded = " ".join(_q(step) for step in steps)
    raw = f'plan {_q(name)}{{steps[{encoded}] parallel {_q("1" if parallel else "0")}}}'
    return optimize_src(raw) if compact else raw


def encode_event(name: str, source: str, key: str = "", session: str = "", compact: bool = False) -> str:
    fields = f"source {_q(source)}"
    if key:
        fields += f" key {_q(key)}"
    if session:
        fields += f" session {_q(session)}"
    raw = f'event {_q(name)}{{{fields} at {_q(_now())}}}'
    return optimize_src(raw) if compact else raw


def encode_state(user_key: str, *, status: str, progress: str = "0", compact: bool = False) -> str:
    raw = (
        f'state "runtime"{{user_key {_q(user_key)} status {_q(status)} '
        f'progress {_q(progress)} at {_q(_now())}}}'
    )
    return optimize_src(raw) if compact else raw


_MODULE = re.compile(r'^(intent|reply|task|event|memory|plan|state)\s+"((?:\.|[^"])*)"\s*\{(.*)\}$', re.DOTALL)
_FIELD = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*(?:"((?:\.|[^"])*)"|\[([^\]]*)\])')
_STRING = re.compile(r'"((?:\.|[^"])*)"')


def parse(text: str) -> dict[str, Any]:
    match = _MODULE.match(text.strip())
    if not match:
        raise ValueError("Invalid ADILang module")
    module, tag, body = match.groups()
    fields: OrderedDict[str, Any] = OrderedDict()
    for field in _FIELD.finditer(body):
        key, scalar, array = field.groups()
        if key in fields:
            raise ValueError(f"Duplicate key: {key}")
        if array is not None:
            fields[key] = [bytes(item, "utf-8").decode("unicode_escape") for item in _STRING.findall(array)]
        else:
            fields[key] = bytes(scalar or "", "utf-8").decode("unicode_escape")
    return {"module": module, "tag": tag, "fields": dict(fields)}


def validate(text: str) -> list[str]:
    try:
        parsed = parse(text)
    except ValueError as exc:
        return [str(exc)]
    module = parsed["module"]
    fields = parsed["fields"]
    errors = []
    for key in fields:
        if key not in MODULE_KEYS[module]:
            errors.append(f"Unknown key for {module}: {key}")
    for key in REQUIRED[module]:
        if key not in fields:
            errors.append(f"Missing required key: {key}")
    if module == "intent" and fields.get("verb", "ask") not in VERBS:
        errors.append("Invalid verb")
    if module == "memory" and "confidence" in fields:
        try:
            value = float(fields["confidence"])
            if not 0 <= value <= 1:
                errors.append("confidence must be 0..1")
        except ValueError:
            errors.append("confidence must be numeric")
    return errors
