# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from typing import Any
from typing import Hashable

import yaml

from esp_gpio_tool_cli.chip import ESP
from esp_gpio_tool_cli.chip import SUPPORTED_CHIPS


# Create a custom YAML loader that checks for duplicate keys
class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        mapping = {}
        for key_node, val_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            val = self.construct_object(val_node, deep=deep)
            if key in mapping:
                raise ValueError(f"Duplicate '{key!r}' key found in YAML.")
            mapping[key] = val
        return mapping


def load_user_input(input_string: str) -> dict[str, str]:
    try:
        return yaml.load(input_string, Loader=UniqueKeyLoader)  # type: ignore
    except yaml.YAMLError as err:
        raise SystemExit(f'Error loading YAML: {err}') from err
    except ValueError as err:
        raise SystemExit(f'Error: Invalid format: {err}') from err


def run_check(user_input: str | dict) -> list[str]:
    output = []
    if isinstance(user_input, str):
        data = load_user_input(user_input)
    else:
        data = user_input
    # get the chip name and verify if it is supported
    if 'chip' not in data.keys():
        output.append('Warning: Chip name not found in input file. Assuming ESP32.')
    chip_name = data.pop('chip', 'esp32')
    if chip_name not in SUPPORTED_CHIPS:
        raise SystemExit(f"Error: Invalid chip: '{chip_name}'. Supported chips: {SUPPORTED_CHIPS}.")
    esp = ESP(chip_name)
    peripherals: dict[str, dict[str, str]] | Any = data.pop('peripheral', {})
    if not isinstance(peripherals, dict):
        raise SystemExit('Error: Invalid format: Peripheral section must be a dictionary.')
    for name, value in peripherals.items():
        try:
            per = esp.get_peripheral(name)
            for i, mode in value.items():
                per.set_mode(str(i), mode)
        except ValueError as err:
            output.append(f'Error: {err}. Mode was NOT changed!')

    # check if the pin is used multiple times and print warning
    for pin, fnc in data.items():
        if isinstance(fnc, list):
            output.append(f'Warning: Pin {pin} has been used multiple times, this may be a mistake, please be aware.')

    # go through the yaml file and check if the pins have valid configuration for selected target
    for key, fun_value in data.items():
        try:
            num = int(key)
        except ValueError:
            output.append(f'Error: Unknown key in yaml: {key}. Skipping.')
            continue
        # Check if the pin is valid
        if num not in esp.gpios.keys():
            output.append(f'Error: Pin {num} not found for {esp.name}.')
            continue

        try:
            if isinstance(fun_value, list):
                for fnc in fun_value:
                    if fnc not in ['INPUT', 'OUTPUT']:
                        # Check if the function is valid and get the peripheral
                        per = esp.get_peripheral_from_function(fnc)

                        # Check if the pin can be used for the function and mark peripheral as used
                        per.use(fnc, esp.gpios[num])
            elif fun_value not in ['INPUT', 'OUTPUT']:
                # Check if the function is valid and get the peripheral
                per = esp.get_peripheral_from_function(fun_value)

                # Check if the pin can be used for the function and mark peripheral as used
                note = per.use(fun_value, esp.gpios[num])
                if note is not None:
                    output.append(note)

            # Check if the pin supports the function
            if isinstance(fun_value, list):
                for fnc in fun_value:
                    output.extend(esp.gpios[num].assign_function(fnc))
            else:
                output.extend(esp.gpios[num].assign_function(fun_value))
        except ValueError as err:
            output.append(f'Error: {err}')
            continue

    # check if all peripherals that has been used have all non-optional pins used
    output.extend(esp.check())
    if not output:
        output.append('All checks passed.')

    # clear the output from duplicates (may occur when the pin is used multiple times)
    real_output = []
    for out in output:
        if out not in real_output:
            real_output.append(out)

    return real_output
