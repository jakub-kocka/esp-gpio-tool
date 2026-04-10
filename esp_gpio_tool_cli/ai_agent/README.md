# Interactive ESP32 GPIO Assignment AI Agent

An AI agent that provides an interactive CLI for ESP32 project design and GPIO pin assignment, powered by OpenAI and the GPIO MCP server.

## Features

- **Interactive Requirement Clarification**: Asks targeted questions only when confidence is low, using arrow-key selection for suggested answers
- **Agent-Driven Design**: The LLM autonomously decides when to query chip info, assign pins, validate configurations, and generate diagrams
- **GPIO Pin Assignment**: Assigns and validates GPIO pins via the MCP server
- **MCP Server Integration**: Connects to the GPIO tool MCP server for real-time chip/pin data and validation
- **Architecture Visualization**: Generates Mermaid diagrams and saves them as interactive HTML files
- **Configurable Model and Thresholds**: Choose the OpenAI model and confidence threshold via CLI flags or environment variables

## Architecture

```txt
                    ┌─────────────────┐
                    │   User Input    │
                    └────────┬────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│                    AI Design Agent                      │
│                    (OpenAI-powered)                     │
│                                                         │
│  • Requirement Analysis & Clarification                 │
│  • Autonomous Tool Orchestration                        │
│  • Mermaid Diagram Generation                           │
└──────────----──────────────┬────────────────────────────┘
                             │
                    ┌────────▼─────────┐
                    │  GPIO Tool MCP   │
                    │     Server       │
                    │                  │
                    │  • Chip Info     │
                    │  • Pin Assignment│
                    │  • Validation    │
                    └──────────────────┘
```

The agent keeps a single MCP session open per run. The LLM decides which tools to call and in what order -- there is no fixed pipeline.

## Installation

1. Install the project with the `ai_agent,mcp` extras:

   ```bash
   pip install -e ".[ai_agent,mcp]"
   ```

2. Set up your OpenAI API key:

   You need an OpenAI API key. Create one at <https://platform.openai.com/api-keys> (paid, requires an OpenAI account). Export your API key so it would be accessible by the script, e.g. on Unix systems you can run following command:

   ```bash
   export OPENAI_API_KEY="your_api_key_here"
   ```

## Usage

### Interactive Mode

Run the agent without arguments to be prompted for requirements:

```bash
python esp_gpio_tool_cli/ai_agent/interactive_agent.py
```

### Providing Initial Requirements

Pass requirements directly on the command line:

```bash
python esp_gpio_tool_cli/ai_agent/interactive_agent.py "Temperature monitor with WiFi and OLED display"
```

## Workflow

1. **Requirement Input**: You describe what you want to build (e.g. "weather station with BME280 and OLED")
2. **Interactive Clarification**: The agent asks clarifying questions only when confidence is below the threshold (default 50%). Use arrow keys to pick a suggestion, type a custom answer, or skip.
3. **Agent-Driven Design**: The LLM autonomously calls MCP tools to:
   - Query supported chips and pick a suitable one
   - Retrieve pin and peripheral information
   - Assign GPIO pins for required peripherals
   - Validate the pin configuration for conflicts
4. **Diagram Generation**: Once the design is ready, the agent generates a Mermaid architecture diagram
5. **Design Summary**: A final summary with pin assignments, warnings, and the diagram is displayed. The diagram is saved as `esp32_diagram.html` for browser viewing.
6. **Save**: Optionally save the full design state to a JSON file

## Configuration

### Environment Variables

| Variable               | Description                                                            | Default              |
|------------------------|------------------------------------------------------------------------|----------------------|
| `OPENAI_API_KEY`       | **Required.** OpenAI API key                                           | --                   |
| `AI_MODEL`             | OpenAI model name                                                      | `gpt-5-nano`         |
| `CONFIDENCE_THRESHOLD` | Threshold below which the agent asks clarifying questions (0.0 -- 1.0) | `0.6`                |
| `GPIO_MCP_SERVER_PATH` | Path to the GPIO MCP server script                                     | `mcp_gpio_server.py` |

All environment variables can also be set via the corresponding CLI flags.

## Troubleshooting

### Common Issues

1. **API Key Not Set**: Ensure the `OPENAI_API_KEY` environment variable is set and valid
2. **MCP Server Not Found**: Ensure `mcp_gpio_server.py` exists in the project root, or set `GPIO_MCP_SERVER_PATH` to the correct path
3. **Agent Loops**: If the agent hits the max tool-round limit (15 by default), check verbose logs (`-v`) for the tool-call history to see what went wrong
