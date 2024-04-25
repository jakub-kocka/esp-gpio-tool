# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import sys

import yaml

from esp_gpio_tool.peripheral import *  # noqa: F403; pylint: disable=wildcard-import, unused-wildcard-import
from esp_gpio_tool.peripheral import BasePeripheral
from esp_gpio_tool.pin import Pin

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'targets/')


def load_config(target: str) -> dict[str, dict]:
    """Load config from yaml file"""
    target = os.path.join(CONFIG_DIR, f'{target}.yaml')
    with open(target, 'r', encoding='UTF-8') as stream:
        try:
            return yaml.safe_load(stream)  # type: ignore
        except yaml.YAMLError as exc:
            raise SystemExit(exc) from exc


class ESP:
    gpios: list[Pin]
    peripherals: list[BasePeripheral]

    def __init__(self, name: str) -> None:
        self.name = name
        self.config = load_config(name)
        self.load_pins()
        self.load_peripherals()

    def _str_to_class(self, name: str) -> type[BasePeripheral]:
        """Convert name to class; defaults to `BasePeripheral` if class not found"""
        return getattr(sys.modules[__name__], name, BasePeripheral)

    def load_pins(self) -> None:
        """Load pins from config"""
        self.gpios = [Pin(pin=number, **data) for number, data in self.config['gpio'].items()]

    def load_peripherals(self) -> None:
        """Load peripherals from config"""
        self.peripherals = [self._str_to_class(peri)(**data) for peri, data in self.config['peripheral'].items()]
