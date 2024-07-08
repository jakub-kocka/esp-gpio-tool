# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import re
import sys

import yaml

from esp_gpio_tool_cli.peripheral import *  # noqa: F403; pylint: disable=wildcard-import, unused-wildcard-import
from esp_gpio_tool_cli.peripheral import BasePeripheral
from esp_gpio_tool_cli.pin import Pin

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'targets/')
SUPPORTED_CHIPS = [filename.split('.')[0] for filename in os.listdir(CONFIG_DIR)]


def load_config(target: str) -> dict[str, dict]:
    """Load config from yaml file"""
    target = os.path.join(CONFIG_DIR, f'{target}.yaml')
    with open(target, 'r', encoding='UTF-8') as stream:
        try:
            return yaml.safe_load(stream)  # type: ignore
        except yaml.YAMLError as exc:
            raise SystemExit(exc) from exc


class ESP:
    gpios: dict[int, Pin]
    peripherals: list[BasePeripheral]
    memory: (
        str | None
    )  # TODO: add option to pick memory type of the chip, and disable selected pins based on the selection

    def __init__(self, name: str) -> None:
        self.name = name
        self.config = load_config(name)
        self.load_pins()
        self.load_peripherals()

    @property
    def assigned_pins(self) -> list[Pin]:
        """Return pins that have been assigned a function"""
        return [pin for pin in self.gpios.values() if pin.assigned_function]

    @property
    def free_pins(self) -> list[Pin]:
        """Return pins that have not been assigned a function"""
        return [pin for pin in self.gpios.values() if not pin.assigned_function]

    @property
    def used_peripherals(self) -> list[BasePeripheral]:
        """Return peripherals that have been used"""
        return [peripheral for peripheral in self.peripherals if any(peripheral.used.values())]

    def _str_to_class(self, name: str) -> type[BasePeripheral]:
        """Convert name to class; defaults to `BasePeripheral` if class not found"""
        return getattr(sys.modules[__name__], name, BasePeripheral)

    def load_pins(self) -> None:
        """Load pins from config"""
        self.gpios = {number: Pin(pin=number, **data) for number, data in self.config['gpio'].items()}

    def load_peripherals(self) -> None:
        """Load peripherals from config"""
        self.peripherals = [self._str_to_class(peri)(**data) for peri, data in self.config['peripheral'].items()]

    def get_peripheral(self, name: str) -> BasePeripheral:
        """Return peripheral with the given name"""
        for peripheral in self.peripherals:
            if peripheral.name == name:
                return peripheral
        raise ValueError(f'Peripheral {name} not found in peripherals for {self.name}.')

    def get_peripheral_from_function(self, function: str) -> BasePeripheral:
        """Return peripheral that uses the function"""
        for peripheral in self.peripherals:
            if re.match(rf'^{peripheral.common_prefix}', function):
                return peripheral
        raise ValueError(f'Function {function} not found in peripherals for {self.name}.')

    def check(self) -> list[str]:
        """Check if required pins by each used peripheral are assigned"""
        out = []
        for peripheral in self.used_peripherals:
            for instance, used in peripheral.used.items():
                if not used:
                    continue
                for function in peripheral.required_pins(instance):
                    for pin in self.gpios.values():
                        if pin.assigned_function == function:
                            break
                    else:
                        out.append(
                            f'Error: Required function {function} from peripheral {peripheral.name} '
                            'is not assigned to any pin.'
                        )
        return out
