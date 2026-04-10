#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
MCP Server for ESP GPIO Tool

This server exposes ESP GPIO tool functionality through the Model Context Protocol,
allowing AI agents to interact with GPIO configuration and validation.
"""

import functools
import json
import logging
from collections.abc import Callable
from typing import Annotated
from typing import Any
from urllib.parse import unquote

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from esp_gpio_tool_cli.checker import run_check
from esp_gpio_tool_cli.chip import ESP
from esp_gpio_tool_cli.chip import SUPPORTED_CHIPS
from esp_gpio_tool_cli.chip import get_peripheral_instance_counts
from esp_gpio_tool_cli.chip import get_pwm_output_capacity

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP('esp-gpio-tool')


def handle_mcp_error(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for consistent error handling"""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error('Error in %s: %s', func.__name__, e, exc_info=True)
            return {'error': str(e), 'function': func.__name__}

    return wrapper


def validate_chip(chip: str) -> None:
    """Validate chip parameter"""
    if chip not in SUPPORTED_CHIPS:
        raise ValueError(f'Unsupported chip: {chip}. Supported chips: {SUPPORTED_CHIPS}')


def validate_pin(chip: str, pin: int) -> None:
    """Validate pin parameter"""
    esp = ESP(chip)
    if pin not in esp.gpios:
        raise ValueError(f'Pin {pin} not available on {chip}')


@mcp.resource('esp://chips')
@handle_mcp_error
async def get_supported_chips() -> str:
    """Get list of supported ESP32 chip variants"""
    return json.dumps({'chips': SUPPORTED_CHIPS})


def _resolve_feature(features: dict, path: str) -> Any:
    """Resolve a dot-separated path like 'connectivity.wifi.supported' in a nested dict."""
    current = features
    for key in path.split('.'):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


@mcp.tool()
@handle_mcp_error
async def find_chips(
    connectivity: Annotated[
        list[str] | None,
        Field(
            description=(
                'Required connectivity features. Each entry is checked against '
                'connectivity.<name>.supported in chip features. '
                'Examples: ["wifi", "bluetooth", "ieee_802154"]. '
                'A chip matches only if ALL listed features have supported=true. '
                'Omit this parameter (or pass null/empty) when the user did not ask for any radio '
                '(WiFi/BT/802.15.4) — do NOT assume wireless unless it is required.'
            ),
        ),
    ] = None,
    peripherals: Annotated[
        list[str] | None,
        Field(
            description=(
                'Required peripheral names. Each entry must match a peripheral name '
                'on the chip (e.g. ["I2C", "TWAI", "SPI"]). '
                'A chip matches only if ALL listed peripherals are present.'
            ),
        ),
    ] = None,
    min_gpios: Annotated[
        int | None,
        Field(description='Minimum number of available GPIOs required.'),
    ] = None,
    min_independent_pwm_outputs: Annotated[
        int | None,
        Field(
            description=(
                'Minimum number of independent on-chip PWM outputs (LEDC SIG_OUT + MCPWM OUT A/B). '
                'Use for servo motor counts, dimmable channels, etc. '
                'Example: 12 servos need min_independent_pwm_outputs=12 (unless using an external driver IC).'
            ),
        ),
    ] = None,
    min_peripheral_instances: Annotated[
        dict[str, int] | None,
        Field(
            description=(
                'Minimum number of independent peripheral *controllers* per type. Keys are peripheral names as in '
                'chip YAML / get_chip_info (e.g. "SPI", "I2C", "UART", "RMT"). Values are required instance counts '
                '(separate SPI masters, UART ports, etc.). Example: three unrelated SPI buses → {"SPI": 3}. '
                'This does not count channels inside one block (e.g. LEDC PWM channels) — use '
                'min_independent_pwm_outputs for that.'
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    """Find chips that match all specified requirements.

    Filters all supported chips by connectivity features, required peripherals,
    minimum GPIO count, optional minimum independent PWM output count, and optional
    minimum per-type peripheral instance counts (SPI controllers, UART ports, etc.).
    Returns matching chips sorted by GPIO count (ascending,
    simplest first) with their features and peripheral names for comparison.

    Example: find_chips(connectivity=["wifi", "ieee_802154"], peripherals=["I2C"])
    returns only chips that have both WiFi and IEEE 802.15.4 radios plus an I2C peripheral.

    Example: find_chips(min_independent_pwm_outputs=12) returns chips with at least 12 combined
    LEDC+MCPWM PWM-style outputs (typical for 12 servos on-chip).

    Example: find_chips(min_peripheral_instances={"SPI": 3}) returns chips with at least three
    independent SPI controller instances (e.g. SPI/HSPI/VSPI or SPI/FSPI/SPI3 depending on chip).
    """
    results = []
    for chip_name in SUPPORTED_CHIPS:
        try:
            esp = ESP(chip_name)
            features = esp.features

            if connectivity:
                match = True
                for conn in connectivity:
                    supported = _resolve_feature(features, f'connectivity.{conn}.supported')
                    if supported is not True:
                        match = False
                        break
                if not match:
                    continue

            if peripherals:
                # Match both p.name and p.__class__.__name__ (e.g. LPSPI has name='Low power SPI')
                chip_periph_names = set()
                for p in esp.peripherals:
                    chip_periph_names.add(p.name)
                    chip_periph_names.add(p.__class__.__name__)
                if not all(req in chip_periph_names for req in peripherals):
                    continue

            if min_gpios is not None and len(esp.gpios) < min_gpios:
                continue

            if min_independent_pwm_outputs is not None:
                cap = get_pwm_output_capacity(esp)
                if cap['max_independent_pwm_outputs'] < min_independent_pwm_outputs:
                    continue

            if min_peripheral_instances:
                meets = True
                for label, min_n in min_peripheral_instances.items():
                    periph = esp.get_peripheral(label)
                    if periph is None or len(periph.instances) < min_n:
                        meets = False
                        break
                if not meets:
                    continue

            results.append(_get_chip_info(chip_name))
        except Exception:
            logger.debug(f'Error getting chip info for {chip_name}', exc_info=True)

    results.sort(key=lambda r: r.get('total_gpios', 0))

    return {
        'matching_chips': [r['chip'] for r in results],
        'count': len(results),
        'chips': results,
    }


@mcp.resource('esp://chip/{chip}')
@handle_mcp_error
async def get_chip_info(chip: str) -> str:
    """Get detailed information about a specific ESP32 chip"""
    result = _get_chip_info(chip)
    return json.dumps(result)


@mcp.resource('esp://chip/{chip}/soc/{soc}')
@handle_mcp_error
async def get_chip_info_with_soc(chip: str, soc: str) -> str:
    """Get detailed information about a specific ESP32 chip with SoC variant"""
    result = _get_chip_info(chip, soc)
    return json.dumps(result)


def _get_chip_info(chip: str, soc: str | None = None) -> dict[str, Any]:
    validate_chip(chip)
    esp = ESP(chip)
    if soc:
        esp.set_soc(soc)

    result = {
        'chip': chip,
        'soc': str(esp.selected_soc) if esp.selected_soc else None,
        'available_socs': [str(s) for s in esp.soc_list],
        'features': esp.features,
        'total_gpios': len(esp.gpios),
        'available_gpios': [pin.pin for pin in esp.free_pins],
        'pwm_output_capacity': get_pwm_output_capacity(esp),
        'peripheral_instance_counts': get_peripheral_instance_counts(esp),
        'peripherals': [
            {
                'name': p.name,
                'count': p.count,
                'instances': p.instances,
                'reassignable': p.reassignable,
                'supported_modes': p.supported_modes,
                'mode': p.mode,
            }
            for p in esp.peripherals
        ],
    }
    return result


@mcp.resource('esp://chip/{chip}/peripheral/{peripheral}')
@handle_mcp_error
async def get_peripheral_info(chip: str, peripheral: str) -> str:
    """Get information about a specific peripheral on a chip"""
    peripheral = unquote(peripheral)
    validate_chip(chip)
    esp = ESP(chip)
    try:
        peripheral_obj = esp.get_peripheral(peripheral)
    except ValueError as e:
        return json.dumps({'error': str(e)})

    result = {
        'name': peripheral_obj.name,
        'count': peripheral_obj.count,
        'instances': peripheral_obj.instances,
        'reassignable': peripheral_obj.reassignable,
        'assigned_pins': peripheral_obj.assigned_pins,
        'universal_pins': peripheral_obj.universal_pins,
        'optional_pins': peripheral_obj.optional_pins,
        'supported_modes': peripheral_obj.supported_modes,
    }
    return json.dumps(result)


@mcp.resource('esp://chip/{chip}/pins')
@handle_mcp_error
async def list_available_pins(chip: str) -> str:
    """List all available GPIO pins for a chip with their capabilities and restrictions"""
    validate_chip(chip)
    esp = ESP(chip)

    pins_info = []
    for pin in esp.free_pins:
        pins_info.append(
            {
                'pin': pin.pin,
                'power_domain': pin.power_domain,
                'is_input': pin.is_input,
                'is_output': pin.is_output,
                'strapping': pin.strapping,
                'functions': pin.functions,
                'at_reset': pin.at_reset,
                'rtc': pin.rtc,
                'lp': pin.lp,
                'is_debug_pin': pin.is_debug_pin,
                'is_serial_pin': pin.is_serial_pin,
            }
        )

    result = {
        'chip': chip,
        'total_available': len(pins_info),
        'pins': pins_info,
    }
    return json.dumps(result)


@mcp.resource('esp://chip/{chip}/pin/{pin}/capabilities')
@handle_mcp_error
async def get_pin_capabilities(chip: str, pin: int) -> str:
    """Get capabilities and restrictions for specific GPIO pins"""
    validate_chip(chip)
    esp = ESP(chip)
    validate_pin(chip, pin)

    pin_obj = esp.gpios[pin]
    result = {
        'pin': pin_obj.pin,
        'power_domain': pin_obj.power_domain,
        'is_input': pin_obj.is_input,
        'is_output': pin_obj.is_output,
        'strapping': pin_obj.strapping,
        'functions': pin_obj.functions,
        'at_reset': pin_obj.at_reset,
        'rtc': pin_obj.rtc,
        'lp': pin_obj.lp,
    }
    return json.dumps(result)


@mcp.resource('esp://chip/{chip}/function/{function}/gpio_list')
@handle_mcp_error
async def get_function_gpio_list(chip: str, function: str) -> str:
    """Get list of GPIO pins that can be assigned to a specific function"""
    validate_chip(chip)
    esp = ESP(chip)
    return json.dumps({'gpio_list': [pin.pin for pin in esp.list_pins_by_function(function)]})


@mcp.resource('esp://chip/{chip}/peripheral/{peripheral}/functions')
@handle_mcp_error
async def get_peripheral_functions(chip: str, peripheral: str) -> str:
    """Get all valid function names for a specific peripheral on a chip.

    Returns the exact function names that should be used with assign_pin_function,
    organized by peripheral instance. Functions are categorized as:
    - assigned_pins: IO MUX functions that must be on specific GPIO pins
    - universal_pins: GPIO matrix functions that can be assigned to any GPIO pin
    """
    peripheral = unquote(peripheral)
    validate_chip(chip)
    esp = ESP(chip)
    try:
        peripheral_obj = esp.get_peripheral(peripheral)
    except ValueError as e:
        available = [p.name for p in esp.peripherals]
        return json.dumps({'error': str(e), 'available_peripherals': available})

    result: dict[str, Any] = {
        'peripheral': peripheral_obj.name,
        'instances': peripheral_obj.instances,
        'reassignable': peripheral_obj.reassignable,
        'functions_by_instance': {},
    }
    for instance in peripheral_obj.instances:
        assigned = peripheral_obj.assigned_pins.get(instance, [])
        universal = peripheral_obj.universal_pins.get(instance, [])
        result['functions_by_instance'][instance] = {
            'assigned_pins': assigned,
            'universal_pins': universal,
            'all_functions': sorted(set(assigned + universal)),
        }
    return json.dumps(result)


@mcp.resource('esp://chip/{chip}/pins/all')
@handle_mcp_error
async def get_all_pins_info(chip: str) -> str:
    """Get comprehensive information about all pins on a chip including functions and assignments"""
    result = _get_all_pins_info(chip)
    return json.dumps(result)


@mcp.resource('esp://chip/{chip}/soc/{soc}/pins/all')
@handle_mcp_error
async def get_all_pins_info_with_soc(chip: str, soc: str) -> str:
    """Get comprehensive information about all pins on a chip with specific SoC
    variant including functions and assignments"""
    result = _get_all_pins_info(chip, soc)
    return json.dumps(result)


def _get_all_pins_info(chip: str, soc: str | None = None) -> dict[str, Any]:
    validate_chip(chip)
    esp = ESP(chip)
    if soc:
        esp.set_soc(soc)

    pins_info = []
    for pin_obj in esp.gpios.values():
        pins_info.append(
            {
                'pin': pin_obj.pin,
                'power_domain': pin_obj.power_domain,
                'is_input': pin_obj.is_input,
                'is_output': pin_obj.is_output,
                'strapping': pin_obj.strapping,
                'functions': pin_obj.functions,
                'at_reset': pin_obj.at_reset,
                'rtc': pin_obj.rtc,
                'lp': pin_obj.lp,
                'is_debug_pin': any(
                    f in ['MTCK', 'MTDO', 'MTMS', 'MTDI', 'USB_D-', 'USB_D+'] for f in pin_obj.functions
                ),
                'is_serial_pin': any(f in ['U0TXD', 'U0RXD'] for f in pin_obj.functions),
                'is_assigned': bool(pin_obj.assigned_functions),
                'assigned_functions': pin_obj.assigned_functions,
            }
        )

    # Get peripheral information for pin assignment
    peripherals_info = []
    for peripheral in esp.peripherals:
        peripherals_info.append(
            {
                'name': peripheral.name,
                'count': peripheral.count,
                'instances': peripheral.instances,
                'reassignable': peripheral.reassignable,
                'assigned_pins': peripheral.assigned_pins,
                'universal_pins': peripheral.universal_pins,
                'optional_pins': peripheral.optional_pins,
                'supported_modes': peripheral.supported_modes,
            }
        )

    result = {
        'chip': chip,
        'soc': str(esp.selected_soc) if esp.selected_soc else None,
        'total_pins': len(pins_info),
        'available_pins': len([p for p in pins_info if not p['is_assigned']]),
        'pins': pins_info,
        'peripherals': peripherals_info,
    }
    return result


@mcp.tool()
@handle_mcp_error
async def validate_pin_config(
    chip: Annotated[
        str,
        Field(description='ESP32 chip name, e.g. "esp32", "esp32s3", "esp32c3".'),
    ],
    pin_assignments: Annotated[
        dict[str, str | list[str]],
        Field(
            description=(
                'REQUIRED. Pin assignments as a dict mapping GPIO number (string) to function name(s). '
                'You MUST provide this parameter. '
                'Example: {"21": "I2C0_SDA", "22": "I2C0_SCL", "1": "U0TXD", "3": "U0RXD"}'
            ),
        ),
    ],
    soc: Annotated[
        str | None,
        Field(description='Optional SoC variant, e.g. "ESP32-D0WD".'),
    ] = None,
    peripheral: Annotated[
        dict[str, dict[str, str]] | None,
        Field(
            description=(
                'Optional peripheral mode configuration. '
                'ONLY include peripherals whose supported_modes is NOT empty. '
                'Check supported_modes from get_peripheral_info first. '
                'If supported_modes is {} (empty), do NOT include that peripheral here. '
                'Example: {"SPI": {"HSPI": "Single SPI"}} (only if SPI has non-empty supported_modes). '
                'Peripherals like I2C and ADC typically have no modes — omit them.'
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    """Validate a complete pin configuration for compatibility and conflicts.

    Checks all pin assignments for the given chip and reports errors/warnings.

    Example call: validate_pin_config(
        chip="esp32",
        pin_assignments={"21": "I2C0_SDA", "22": "I2C0_SCL"}
    )

    Only pass peripheral modes for peripherals with non-empty supported_modes.
    Example with SPI mode: validate_pin_config(
        chip="esp32",
        pin_assignments={"14": "HSPICLK", "12": "HSPIQ", "13": "HSPID"},
        peripheral={"SPI": {"HSPI": "Single SPI"}}
    )
    """
    config: dict[str, Any] = {'chip': chip}
    if soc:
        config['soc'] = soc
    if peripheral:
        config['peripheral'] = peripheral
    # Only add pin assignment keys; reserved keys come from parameters only
    reserved = {'chip', 'soc', 'peripheral'}
    for k, v in pin_assignments.items():
        if k not in reserved:
            config[k] = v

    output = run_check(config)

    result = {
        'valid': not any('Error:' in msg for msg in output),
        'messages': output,
    }
    return result


@mcp.tool()
@handle_mcp_error
async def assign_pin_function(chip: str, pin: int, function: str, soc: str | None = None) -> dict[str, Any]:
    """Assign a specific function to a GPIO pin.

    IMPORTANT: Use exact function names from the peripheral definitions, not generic names.
    Call get_peripheral_functions first to discover valid names.
    Examples: 'I2C0_SDA' (not 'SDA'), 'U0TXD' (not 'UART0_TX'), 'LEDC_SIG_OUT0' (not 'PWM'),
    'ADC1_CH6' (not 'ADC').

    Args:
        chip: ESP32 chip name (e.g. esp32, esp32s3)
        pin: GPIO pin number
        function: Exact function/signal name to assign (e.g. I2C0_SDA, LEDC_SIG_OUT0, ADC1_CH6)
        soc: Optional: Specific SoC variant
    """
    validate_chip(chip)
    esp = ESP(chip)
    if soc:
        esp.set_soc(soc)

    validate_pin(chip, pin)
    pin_obj = esp.gpios[pin]

    if function.upper() in ('INPUT', 'OUTPUT', 'INPUT/OUTPUT'):
        pin_obj.assign_function(function.upper())
        return {
            'success': True,
            'pin': pin,
            'function': function.upper(),
            'pin_info': {
                'pin': pin_obj.pin,
                'assigned_functions': pin_obj.assigned_functions,
                'power_domain': pin_obj.power_domain,
                'functions': pin_obj.functions,
            },
        }

    if function not in pin_obj.functions:
        # Not a direct IO MUX function on this pin; check peripheral definitions
        try:
            peripheral = esp.get_peripheral_from_function(function)
        except ValueError:
            return {
                'success': False,
                'error': f'Function "{function}" not found in any peripheral',
                'hint': (
                    'Use exact function names from peripheral definitions. '
                    'Call get_peripheral_functions to discover valid names. '
                    'Common examples: I2C0_SDA, U0TXD, LEDC_SIG_OUT0, ADC1_CH6, HSPICLK.'
                ),
            }

        # Found the peripheral - verify the function is a valid pin name
        is_valid = any(function in pins for pins in peripheral.all_pins.values())
        if not is_valid:
            all_functions = sorted({f for pins in peripheral.all_pins.values() for f in pins})
            return {
                'success': False,
                'error': f'"{function}" is not a valid function name for {peripheral.name} peripheral',
                'valid_functions': all_functions,
            }

        # Valid function name. Check if it can be placed on this pin.
        is_universal = any(function in pins for pins in peripheral.universal_pins.values())
        if not is_universal and not peripheral.reassignable:
            # IO MUX function that must be on a specific pin
            valid_pins = [p.pin for p in esp.gpios.values() if function in p.functions]
            return {
                'success': False,
                'error': f'Pin {pin} does not support function {function} (requires specific IO MUX pin)',
                'valid_pins_for_function': valid_pins,
                'pin_info': {
                    'pin': pin_obj.pin,
                    'functions': pin_obj.functions,
                },
            }

    # Assign the function
    pin_obj.assign_function(function)

    result = {
        'success': True,
        'pin': pin,
        'function': function,
        'pin_info': {
            'pin': pin_obj.pin,
            'assigned_functions': pin_obj.assigned_functions,
            'power_domain': pin_obj.power_domain,
            'functions': pin_obj.functions,
        },
    }
    return result


if __name__ == '__main__':
    mcp.run(transport='stdio')
