# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
ESP32 GPIO Assignment Agent — Backend (UI-free).

Core logic for:
- Clarifying requirements (returns structured data; no prompts)
- GPIO pin assignment via MCP server
- Mermaid diagram generation
- Design workflow (run_agent_design_with_mcp_tools, run_agent_design_for_web)

This module has no CLI or GUI dependencies. Use from CLI (interactive_agent.py)
or from a future GUI by calling the same API.
"""

import json
import logging
import os
import sys
import typing as t
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from mcp import ClientSession
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI

from .constants import _MERMAID_INVALID_EDGE_RE
from .constants import _MERMAID_QUOTED_SOURCE_NODE_RE
from .constants import _MERMAID_UNCLOSED_PIPE_RE
from .constants import DEFAULT_CONFIDENCE_THRESHOLD
from .constants import DEFAULT_MAX_TOOL_ROUNDS
from .constants import DEFAULT_MODEL
from .constants import DEFAULT_SYSTEM_PROMPT
from .constants import DESIGN_PROMPT_TEMPLATE
from .constants import MAX_CONVERSATION_HISTORY_ENTRIES
from .constants import SYSTEM_PROMPT_ASK_CLARIFYING_QUESTIONS
from .constants import SYSTEM_PROMPT_GENERATE_ARCHITECTURE_DIAGRAM

logger = logging.getLogger('esp_gpio_agent')

# Tunables (could be made CLI/config later)


def validate_mermaid(diagram: str) -> list[str]:
    """Return a list of issues found in the Mermaid diagram. Empty list means valid."""
    issues: list[str] = []
    if not diagram.strip():
        issues.append('Diagram is empty.')
        return issues
    for i, line in enumerate(diagram.splitlines(), 1):
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith('%%')
            or stripped.startswith('classDef')
            or stripped.startswith('class ')
        ):
            continue
        if _MERMAID_INVALID_EDGE_RE.search(stripped):
            issues.append(f'Line {i}: invalid edge syntax in "{stripped}"')
        if _MERMAID_QUOTED_SOURCE_NODE_RE.search(stripped):
            issues.append(
                f'Line {i}: source node (left of arrow) must not be in quotes; '
                f'use NodeName not "NodeName" in "{stripped}"'
            )
        if _MERMAID_UNCLOSED_PIPE_RE.search(stripped):
            pipe_count = stripped.count('|')
            if pipe_count % 2 != 0:
                issues.append(f'Line {i}: unclosed pipe label (missing closing |) in "{stripped}"')
    return issues


def create_mermaid_html(diagram: str) -> str:
    """Create a Mermaid HTML diagram."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESP32 GPIO Assignment Diagram</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }}
        .diagram-container {{
            border: 2px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            background: #fafafa;
            margin: 20px 0;
        }}
        .mermaid {{
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔧 ESP32 GPIO Assignment Diagram</h1>
        <div class="diagram-container">
            <div class="mermaid">
{diagram.replace('```mermaid', '').replace('```', '')}
            </div>
        </div>
    </div>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            themeVariables: {{
                primaryColor: '#ff6b35',
                primaryTextColor: '#fff',
                primaryBorderColor: '#ff6b35',
                lineColor: '#333',
                secondaryColor: '#006100',
                tertiaryColor: '#fff'
            }}
        }});
    </script>
</body>
</html>"""


GPIO_RESOURCE_TOOLS = [
    {
        'name': 'get_supported_chips',
        'description': 'Get list of supported ESP32 chip variants (e.g. esp32, esp32s3, esp32c3).',
        'parameters': {'type': 'object', 'properties': {}, 'required': []},
        'uri_template': 'esp://chips',
    },
    {
        'name': 'get_chip_info',
        'description': (
            'Get detailed information about a specific ESP32 chip including features '
            '(CPU cores/frequency, memory, connectivity: WiFi/BT/802.15.4/Ethernet/USB, security), '
            'GPIO count, and peripherals. Use features to compare chips and select the best fit.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {'chip': {'type': 'string', 'description': 'Chip name, e.g. esp32, esp32s3'}},
            'required': ['chip'],
        },
        'uri_template': 'esp://chip/{chip}',
    },
    {
        'name': 'get_all_pins_info',
        'description': 'Get comprehensive info for all pins on a chip: functions, assignments, peripherals.',
        'parameters': {
            'type': 'object',
            'properties': {'chip': {'type': 'string', 'description': 'Chip name'}},
            'required': ['chip'],
        },
        'uri_template': 'esp://chip/{chip}/pins/all',
    },
    {
        'name': 'get_peripheral_info',
        'description': 'Get information about a specific peripheral (e.g. I2C, SPI, UART) on a chip.',
        'parameters': {
            'type': 'object',
            'properties': {
                'chip': {'type': 'string'},
                'peripheral': {'type': 'string', 'description': 'Peripheral name, e.g. I2C, SPI, UART'},
            },
            'required': ['chip', 'peripheral'],
        },
        'uri_template': 'esp://chip/{chip}/peripheral/{peripheral}',
    },
    {
        'name': 'list_available_pins',
        'description': 'List available (free) GPIO pins for a chip with capabilities and restrictions.',
        'parameters': {
            'type': 'object',
            'properties': {'chip': {'type': 'string'}},
            'required': ['chip'],
        },
        'uri_template': 'esp://chip/{chip}/pins',
    },
    {
        'name': 'get_pin_capabilities',
        'description': 'Get capabilities and restrictions for a specific GPIO pin.',
        'parameters': {
            'type': 'object',
            'properties': {
                'chip': {'type': 'string'},
                'pin': {'type': 'integer', 'description': 'GPIO number'},
            },
            'required': ['chip', 'pin'],
        },
        'uri_template': 'esp://chip/{chip}/pin/{pin}/capabilities',
    },
    {
        'name': 'get_peripheral_functions',
        'description': (
            'Get all valid function names for a specific peripheral. '
            'ALWAYS call this before assign_pin_function to discover exact function names '
            '(e.g. I2C0_SDA, U0TXD, LEDC_SIG_OUT0, ADC1_CH6). '
            'Returns functions organized by instance with assigned_pins (IO MUX) and universal_pins (GPIO matrix).'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'chip': {'type': 'string'},
                'peripheral': {
                    'type': 'string',
                    'description': 'Peripheral name, e.g. I2C, SPI, UART, ADC, LEDC, MCPWM',
                },
            },
            'required': ['chip', 'peripheral'],
        },
        'uri_template': 'esp://chip/{chip}/peripheral/{peripheral}/functions',
    },
    {
        'name': 'get_function_gpio_list',
        'description': (
            'Get list of GPIO pins that can be assigned to a specific function. '
            'Use exact function names (e.g. I2C0_SDA, ADC1_CH6, LEDC_SIG_OUT0). '
            'For universal pins (GPIO matrix), returns all free pins.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'chip': {'type': 'string'},
                'function': {
                    'type': 'string',
                    'description': 'Exact function name, e.g. I2C0_SDA, ADC1_CH6, LEDC_SIG_OUT0',
                },
            },
            'required': ['chip', 'function'],
        },
        'uri_template': 'esp://chip/{chip}/function/{function}/gpio_list',
    },
]

MERMAID_DIAGRAM_TOOL = {
    'type': 'function',
    'function': {
        'name': 'generate_mermaid_diagram',
        'description': (
            'Generate a Mermaid diagram of the ESP32 application architecture. '
            'Call this when you have gathered requirements, pin assignments, and optionally components. '
            'Provide a clear design_context string describing the project, peripherals, pin assignments, and components'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'design_context': {
                    'type': 'string',
                    'description': (
                        'Text describing the ESP32 project: application type, chip, '
                        'pin assignments (peripheral -> pins), and key components.'
                    ),
                },
            },
            'required': ['design_context'],
        },
    },
}


def _safe_json_parse(text: str | None, default: dict[str, t.Any] | None = None) -> dict[str, t.Any]:
    if not text or not text.strip():
        return default or {}
    try:
        return t.cast(dict[str, t.Any], json.loads(text))
    except json.JSONDecodeError:
        return default or {'raw': text}


def _mcp_tool_to_openai(mcp_tool: t.Any) -> dict[str, t.Any]:
    name = getattr(mcp_tool, 'name', None) or mcp_tool.get('name', '')
    description = getattr(mcp_tool, 'description', None) or mcp_tool.get('description', '') or ''
    schema = getattr(mcp_tool, 'inputSchema', None) or mcp_tool.get('inputSchema') or {}
    params = schema if isinstance(schema, dict) else {}
    if not params:
        params = {'type': 'object', 'properties': {}, 'required': []}
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description or f'Call MCP tool {name}',
            'parameters': params,
        },
    }


def _build_openai_tools(mcp_tools_result: t.Any, include_resources: bool = True) -> list[dict[str, t.Any]]:
    openai_tools: list[dict[str, t.Any]] = []
    tools_list = getattr(mcp_tools_result, 'tools', mcp_tools_result) if hasattr(mcp_tools_result, 'tools') else []
    if isinstance(tools_list, list):
        for tool in tools_list:
            openai_tools.append(_mcp_tool_to_openai(tool))
    if include_resources:
        for r in GPIO_RESOURCE_TOOLS:
            openai_tools.append(
                {
                    'type': 'function',
                    'function': {
                        'name': r['name'],
                        'description': r['description'],
                        'parameters': r['parameters'],
                    },
                }
            )
    return openai_tools


class InteractiveGPIOAgent:
    """
    Backend agent for ESP32 GPIO assignment and design.

    No UI: all methods return data or raise. Call from CLI (interactive_agent) or GUI.
    """

    def __init__(
        self,
        openai_api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ):
        self.openai_api_key = openai_api_key or os.environ.get('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError('OPENAI_API_KEY must be provided or set as environment variable')

        self.openai_client = OpenAI(api_key=self.openai_api_key)
        self.model = model
        self.gpio_server_params: StdioServerParameters | None = None
        self.conversation_history: list[dict[str, t.Any]] = []
        self.current_requirements: dict[str, t.Any] = {}
        self.design_state: dict[str, t.Any] = {}
        self.confidence_threshold = confidence_threshold

    async def start_mcp_servers(self) -> None:
        """Configure GPIO MCP server (agent calls it via tools). No UI output."""
        project_root = Path(__file__).resolve().parent
        mcp_script = os.environ.get('GPIO_MCP_SERVER_PATH', 'mcp_gpio_server.py')
        if not os.path.isabs(mcp_script):
            mcp_script = str(project_root / mcp_script)
        if not os.path.exists(mcp_script):
            raise FileNotFoundError(f'MCP server script not found: {mcp_script}')
        self.gpio_server_params = StdioServerParameters(
            command=sys.executable,
            args=[mcp_script],
            env=None,
            cwd=str(project_root),
        )
        logger.info('GPIO MCP server configured')
        logger.debug('MCP server: command=%r args=%s cwd=%s', sys.executable, mcp_script, project_root)

    @asynccontextmanager
    async def _with_gpio_mcp_session(self) -> t.AsyncGenerator[ClientSession, None]:
        if not self.gpio_server_params:
            raise RuntimeError('GPIO MCP server not initialized')
        logger.info('Starting local GPIO MCP server (stdio)...')
        async with stdio_client(self.gpio_server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logger.info('Local GPIO MCP server connected (session initialized)')
                yield session

    def create_design_prompt(self, requirements: str) -> str:
        return DESIGN_PROMPT_TEMPLATE.format(requirements=requirements)

    async def _execute_tool_with_session(
        self, session: ClientSession, tool_name: str, arguments: dict[str, t.Any]
    ) -> dict[str, t.Any]:
        resource_def = next((r for r in GPIO_RESOURCE_TOOLS if r['name'] == tool_name), None)
        if resource_def:
            uri_args = dict(arguments)
            if 'peripheral' in uri_args and isinstance(uri_args['peripheral'], str):
                uri_args['peripheral'] = quote(uri_args['peripheral'], safe='')
            if 'function' in uri_args and isinstance(uri_args['function'], str):
                uri_args['function'] = quote(uri_args['function'], safe='')
            uri = t.cast(str, resource_def['uri_template']).format(**uri_args)
            logger.debug('MCP server: read_resource %s', uri)
            result = await session.read_resource(uri)
            if result.contents:
                text = result.contents[0].text
                logger.debug('MCP server: read_resource result %s', text)
                return _safe_json_parse(text, default={'raw': text})
            return {'error': 'Empty resource'}
        logger.debug('MCP server: call_tool %s %s', tool_name, arguments)
        result = await session.call_tool(tool_name, arguments)
        logger.debug('MCP server: tool result %s', result)
        if result.isError:
            error_text = result.content[0].text if result.content else 'Unknown MCP tool error'
            return {'error': error_text}
        if result.content:
            text = result.content[0].text
            parsed = _safe_json_parse(text, default={'raw': text})
            if parsed.get('success') is False:
                parsed.setdefault('error', parsed.get('raw', 'Tool returned success=false'))
            return parsed
        return {'error': 'Empty tool result'}

    def _strip_mermaid_fences(self, content: str) -> str:
        if content.startswith('```'):
            lines = content.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            content = '\n'.join(lines)
        return content

    async def _run_generate_mermaid_diagram_tool(self, arguments: dict[str, t.Any]) -> dict[str, t.Any]:
        design_context = arguments.get('design_context', '') or ''
        if not design_context.strip():
            return {'error': 'design_context is required', 'mermaid': ''}

        max_attempts = 2
        messages: list[dict[str, str]] = [
            {'role': 'system', 'content': SYSTEM_PROMPT_GENERATE_ARCHITECTURE_DIAGRAM},
            {
                'role': 'user',
                'content': f'Create a Mermaid diagram for this ESP32 project:\n\n{design_context}',
            },
        ]

        for attempt in range(max_attempts):
            try:
                response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                )
                content = self._strip_mermaid_fences((response.choices[0].message.content or '').strip())

                issues = validate_mermaid(content)
                if not issues:
                    logger.debug('Mermaid diagram generated successfully')
                    return {'mermaid': content, 'message': 'Diagram generated.'}

                if attempt < max_attempts - 1:
                    logger.warning('Mermaid validation failed (attempt %d): %s', attempt + 1, issues)
                    messages.append({'role': 'assistant', 'content': f'```mermaid\n{content}\n```'})
                    messages.append(
                        {
                            'role': 'user',
                            'content': (
                                'The diagram has syntax errors. Fix these issues:\n'
                                + '\n'.join(f'- {i}' for i in issues)
                                + '\n\nRemember: use ONLY valid edges (-->, ---, -.->), '
                                'and for labels use -->|label| with NO spaces inside pipes. '
                                'Do not put node names in quotes (e.g. ESP32C6 --> I2C not "ESP32C6" --> I2C). '
                                'Never use ---|>. Return ONLY the corrected Mermaid code.'
                            ),
                        }
                    )
                else:
                    logger.warning('Mermaid validation still failing after %d attempts: %s', max_attempts, issues)
                    return {
                        'mermaid': content,
                        'message': 'Diagram generated with warnings.',
                        'warnings': issues,
                    }
            except Exception as e:
                return {'error': str(e), 'mermaid': ''}

        return {'error': 'Unexpected state in diagram generation', 'mermaid': ''}

    async def run_agent_design_with_mcp_tools(
        self,
        user_message: str,
        system_prompt: str | None = None,
        *,
        max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    ) -> tuple[str, str | None]:
        """
        Run an agentic design step: the LLM decides when to call MCP and local tools.

        Returns (final_assistant_message, mermaid_diagram_or_none).
        """

        system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        messages: list[dict[str, t.Any]] = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message},
        ]

        captured_diagram: str | None = None
        tool_call_history: list[tuple[int, str]] = []
        consecutive_failures: dict[str, int] = {}
        max_consecutive_failures = 2

        async with self._with_gpio_mcp_session() as session:
            tools_result = await session.list_tools()
            openai_tools = _build_openai_tools(tools_result, include_resources=True)
            openai_tools.append(MERMAID_DIAGRAM_TOOL)

            for round_num in range(max_tool_rounds):
                if round_num == max_tool_rounds - 5 and round_num > 0:
                    messages.append(
                        {
                            'role': 'user',
                            'content': (
                                'Reminder: you have used many tool rounds. '
                                'Please provide your final summary now as a direct text response '
                                '— do not call any more tools.'
                            ),
                        }
                    )
                    logger.debug(
                        'Agent round %s: injected reminder to finish (max_tool_rounds=%s)',
                        round_num + 1,
                        max_tool_rounds,
                    )

                response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice='auto',
                )
                msg = response.choices[0].message
                finish_reason = getattr(response.choices[0], 'finish_reason', None)

                if not getattr(msg, 'tool_calls', None) or not msg.tool_calls:
                    logger.debug(
                        'Agent finished after round %s with final answer (finish_reason=%s)',
                        round_num + 1,
                        finish_reason,
                    )
                    return ((msg.content or '').strip(), captured_diagram)

                tool_names = [tc.function.name for tc in msg.tool_calls]
                for name in tool_names:
                    tool_call_history.append((round_num + 1, name))
                logger.debug('Agent round %s: tool_calls=%s', round_num + 1, tool_names)

                messages.append(
                    {
                        'role': 'assistant',
                        'content': msg.content,
                        'tool_calls': [
                            {
                                'id': tc.id,
                                'type': 'function',
                                'function': {
                                    'name': tc.function.name,
                                    'arguments': tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )

                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        args = {}

                    if consecutive_failures.get(name, 0) >= max_consecutive_failures:
                        result = {
                            'error': f'Tool {name} has failed {max_consecutive_failures} times consecutively. '
                            'Skip this tool and proceed with the information you already have.',
                        }
                        logger.warning(
                            'Skipping tool %s after %d consecutive failures',
                            name,
                            max_consecutive_failures,
                        )
                    else:
                        try:
                            if name == 'generate_mermaid_diagram':
                                result = await self._run_generate_mermaid_diagram_tool(args)
                                if result.get('mermaid'):
                                    captured_diagram = result['mermaid']
                            else:
                                result = await self._execute_tool_with_session(session, name, args)
                        except Exception as e:
                            result = {'error': str(e)}
                            logger.warning('Tool %s failed: %s', name, e)

                    is_error = bool(result.get('error')) or bool(result.get('isError'))
                    if is_error:
                        consecutive_failures[name] = consecutive_failures.get(name, 0) + 1
                    else:
                        consecutive_failures[name] = 0

                    messages.append(
                        {
                            'role': 'tool',
                            'tool_call_id': tc.id,
                            'content': json.dumps(result),
                        }
                    )

            last_10 = tool_call_history[-10:] if len(tool_call_history) > 10 else tool_call_history
            logger.warning(
                'Agent hit max_tool_rounds=%s without a final answer. Total tool calls: %s. Last 10: %s',
                max_tool_rounds,
                len(tool_call_history),
                last_10,
            )
            last_assistant = next(
                (
                    m.get('content') or ''
                    for m in reversed(messages)
                    if m.get('role') == 'assistant' and m.get('content')
                ),
                None,
            )
            if last_assistant and isinstance(last_assistant, str) and last_assistant.strip():
                return (last_assistant.strip(), captured_diagram)
            return (
                'Agent reached max tool rounds without a final answer. '
                f'(Used {len(tool_call_history)} tool calls in {max_tool_rounds} rounds. '
                'Check logs for tool_call_history.)',
                captured_diagram,
            )

    async def ask_clarifying_questions(self, requirements: str) -> dict[str, t.Any]:
        """Return structured clarification result (needs_clarification, questions, confidence, etc.). No UI."""
        user_prompt = f"""User Requirements: "{requirements}"

Based on these requirements, determine if you need to ask clarifying questions to better understand
what they want to build.

Current conversation history:
{self._format_conversation_history()}

Ask a clarifying question if needed, or indicate that requirements are clear enough to proceed."""

        fallback = {'needs_clarification': False, 'question': '', 'suggestions': [], 'confidence': 0.0}
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        'role': 'system',
                        'content': SYSTEM_PROMPT_ASK_CLARIFYING_QUESTIONS.format(
                            confidence_threshold=self.confidence_threshold
                        ),
                    },
                    {'role': 'user', 'content': user_prompt},
                ],
            )
            response_text = response.choices[0].message.content or ''
            logger.debug('Clarification response text: %s', response_text)
            # find() returns -1 when missing; never slice with -1 (that indexes from the end).
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            if start_idx < 0 or end_idx < start_idx:
                logger.warning(
                    'Clarification response has no JSON object (start=%s end=%s)',
                    start_idx,
                    end_idx,
                )
                return fallback
            json_str = response_text[start_idx : end_idx + 1]
            return _safe_json_parse(json_str, default=fallback) or fallback
        except Exception as e:
            logger.warning('Error generating clarifying questions: %s', e)
            return fallback

    def _format_conversation_history(self) -> str:
        if not self.conversation_history:
            return 'No previous conversation.'
        history = []
        for i, entry in enumerate(self.conversation_history[-MAX_CONVERSATION_HISTORY_ENTRIES:], 1):
            history.append(f'{i}. {entry["type"]}: {entry["content"]}')
        return '\n'.join(history)

    def add_to_conversation(self, content_type: str, content: str) -> None:
        self.conversation_history.append({'type': content_type, 'content': content})

    async def run_agent_design_for_web(self, requirements: str) -> dict[str, t.Any]:
        """Run agent-driven design. Returns design_state with summary and diagram. For web/GUI use."""
        await self.start_mcp_servers()
        design_prompt = f"""Design an ESP32 GPIO assignment for this project:

{requirements}

Use your tools to:
1. Get chip/pin info
2. Assign pins
3. Validate the pin configuration
4. Call generate_mermaid_diagram when ready. Then summarize the result."""
        summary, diagram = await self.run_agent_design_with_mcp_tools(design_prompt)
        return {'summary': summary, 'diagram': diagram or ''}
