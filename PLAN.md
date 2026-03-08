# 0.2.0 -- Tool Execution Layer Implementation Plan

## Goal

Extend the existing local‑first orchestration PoC with a **deterministic
tool execution layer**.

The system should allow agents to **request tool execution in structured
JSON**, while a centralized **executor** performs the action. This keeps
the architecture safe, inspectable, and deterministic.

This phase **does not introduce**:

-   autonomous loops
-   agent collaboration
-   memory systems
-   async queues
-   retries
-   cloud brokers

Those belong to later phases.

------------------------------------------------------------------------

# Target Architecture

Current:

User → Router → Agent → Text Response

After 0.2.0:

User\
↓\
Intent Router\
↓\
Selected Agent\
↓\
Agent JSON Output\
↓\
Action Parser\
↓\
Tool Executor\
↓\
Tool Result\
↓\
Response to UI

Key design rule:

**Agents never execute tools directly.** Only the **ToolExecutor** can
run tools.

------------------------------------------------------------------------

# Directory Layout

Add the following structure to the project:

    /core
        router.py
        agent_registry.py
        tools.py            ← NEW (tool system)
        executor.py         ← optional split (can remain in tools.py)

    /tools
        filesystem.py       ← example tool

    bootstrap_tools.py      ← registers tools

    PLAN.md

------------------------------------------------------------------------

# Logging Requirements

All components must emit structured logs.

Example format:

    logger.info(
        "event_name",
        key=value
    )

Key log events:

Router:

    intent_router
    intent=<intent>
    confidence=<score>

Agent:

    agent_selected
    agent=<agent_name>

Executor:

    executor_received
    action=<action>
    tool=<tool>

Tool:

    tool_execute
    tool=<name>
    args=<args>

Tool result:

    tool_result
    tool=<name>
    result_type=<type>

Parsing errors:

    agent_output_parse_error

------------------------------------------------------------------------

# Tool System Implementation

Create:

    core/tools.py

Include the following implementation.

``` python
import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict, Any

logger = logging.getLogger(__name__)


# -----------------------------
# Tool Definition
# -----------------------------

@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, str]
    function: Callable[..., Any]

    def execute(self, args: Dict[str, Any]) -> Any:
        logger.info(
            "tool_execute",
            tool=self.name,
            args=args
        )

        result = self.function(**args)

        logger.info(
            "tool_execute_complete",
            tool=self.name,
            result_type=type(result).__name__
        )

        return result


# -----------------------------
# Tool Registry
# -----------------------------

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, str],
        function: Callable
    ):

        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")

        tool = Tool(
            name=name,
            description=description,
            input_schema=input_schema,
            function=function,
        )

        self._tools[name] = tool

        logger.info(
            "tool_registered",
            tool=name,
            schema=input_schema
        )

    def get(self, name: str) -> Tool:

        logger.info(
            "tool_lookup",
            tool=name
        )

        if name not in self._tools:
            logger.error(
                "tool_lookup_failed",
                tool=name
            )
            raise ValueError(f"Unknown tool: {name}")

        return self._tools[name]

    def list(self):

        logger.info(
            "tool_list_requested",
            count=len(self._tools)
        )

        return list(self._tools.keys())


# -----------------------------
# Agent Action Model
# -----------------------------

class AgentAction:

    def __init__(
        self,
        action: str,
        tool: str | None = None,
        args: Dict[str, Any] | None = None,
        content: str | None = None
    ):

        self.action = action
        self.tool = tool
        self.args = args or {}
        self.content = content

    @classmethod
    def from_dict(cls, data: Dict):

        logger.info(
            "agent_action_parsed",
            action=data.get("action"),
            tool=data.get("tool")
        )

        return cls(
            action=data.get("action"),
            tool=data.get("tool"),
            args=data.get("args"),
            content=data.get("content")
        )


# -----------------------------
# Executor
# -----------------------------

class ToolExecutor:

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def execute(self, action: AgentAction):

        logger.info(
            "executor_received",
            action=action.action,
            tool=action.tool
        )

        if action.action == "respond":

            logger.info(
                "executor_direct_response"
            )

            return action.content

        if action.action == "tool":

            tool = self.registry.get(action.tool)

            result = tool.execute(action.args)

            logger.info(
                "tool_result",
                tool=action.tool,
                result_type=type(result).__name__
            )

            return result

        logger.error(
            "executor_unknown_action",
            action=action.action
        )

        raise ValueError(f"Unknown action type: {action.action}")


# -----------------------------
# Agent Output Parsing
# -----------------------------

def parse_agent_output(raw: str) -> AgentAction:

    logger.info(
        "agent_output_received",
        raw=raw
    )

    try:

        data = json.loads(raw)

        return AgentAction.from_dict(data)

    except Exception as e:

        logger.error(
            "agent_output_parse_error",
            error=str(e),
            raw=raw
        )

        raise
```

------------------------------------------------------------------------

# Example Tool

Create:

    tools/filesystem.py

``` python
from pathlib import Path


def read_file(path: str) -> str:

    p = Path(path)

    if not p.exists():
        return f"File not found: {path}"

    return p.read_text()
```

------------------------------------------------------------------------

# Tool Registration

Create:

    bootstrap_tools.py

``` python
from core.tools import ToolRegistry
from tools.filesystem import read_file

tool_registry = ToolRegistry()

tool_registry.register(
    name="read_file",
    description="Read a local file",
    input_schema={
        "path": "string"
    },
    function=read_file
)
```

------------------------------------------------------------------------

# Agent Output Contract

Agents must return **strict JSON**.

Example tool call:

``` json
{
  "action": "tool",
  "tool": "read_file",
  "args": {
    "path": "notes.md"
  }
}
```

Example direct response:

``` json
{
  "action": "respond",
  "content": "Here is the answer."
}
```

Agents should **never output plain text**.

------------------------------------------------------------------------

# Integration With Existing API Layer

Example request handler:

``` python
from core.tools import ToolExecutor, parse_agent_output
from bootstrap_tools import tool_registry

executor = ToolExecutor(tool_registry)


def handle_request(user_input):

    agent_output = agent.run(user_input)

    action = parse_agent_output(agent_output)

    result = executor.execute(action)

    return result
```

------------------------------------------------------------------------

# Expected Debug Logs

Example execution trace:

    intent_router intent=filesystem confidence=0.92

    agent_selected agent=filesystem_agent

    agent_output_received raw={"action":"tool","tool":"read_file","args":{"path":"notes.md"}}

    agent_action_parsed action=tool tool=read_file

    executor_received action=tool tool=read_file

    tool_lookup tool=read_file

    tool_execute tool=read_file args={'path': 'notes.md'}

    tool_execute_complete tool=read_file result_type=str

    tool_result tool=read_file result_type=str

------------------------------------------------------------------------

# Acceptance Criteria

Implementation is complete when:

✔ Tools can be registered\
✔ Agents can request tool execution via JSON\
✔ ToolExecutor executes tools deterministically\
✔ All execution steps produce structured logs\
✔ Invalid tool calls raise clear errors\
✔ Direct responses bypass tool execution

------------------------------------------------------------------------

# 0.2.0 Complete

Once this layer is implemented, the system will support:

-   filesystem tools
-   API tools
-   vector search tools
-   database tools
-   shell execution
-   RAG retrieval

without changing the architecture.

The next phase will introduce:

**Task Graph / Planner orchestration for multi‑agent workflows.**
