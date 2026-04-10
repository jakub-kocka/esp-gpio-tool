# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from dataclasses import field
from functools import cached_property

from esp_gpio_tool_cli.logger import Logger

logger = Logger()

DEBUG_FUCTIONS = ['MTCK', 'MTDO', 'MTMS', 'MTDI', 'USB_D-', 'USB_D+']
SERIAL_FUCTIONS = ['U0TXD', 'U0RXD']


@dataclass
class Pin:
    pin: int
    power_domain: str
    is_input: bool = True
    is_output: bool = True
    strapping: str | None = None
    functions: list[str] = field(default_factory=list)
    at_reset: str | None = None
    assigned_functions: list[str] = field(default_factory=list)
    rtc: bool = False
    lp: bool = False

    @property
    def used(self) -> bool:
        return bool(self.assigned_functions)

    @cached_property
    def is_debug_pin(self) -> bool:
        return any(f in DEBUG_FUCTIONS for f in self.functions)

    @cached_property
    def is_serial_pin(self) -> bool:
        return any(f in SERIAL_FUCTIONS for f in self.functions)

    def __str__(self) -> str:
        return f'GPIO{self.pin} - {self.power_domain}'

    def __repr__(self) -> str:
        return str(self)

    def assign_function(self, function: str) -> None:
        # Check for pin compatibility
        function = function.upper()
        if function == 'INPUT' and not self.is_input:
            raise ValueError(f'Pin {self.pin} does not support input mode.')
        if function == 'OUTPUT' and not self.is_output:
            raise ValueError(f'Pin {self.pin} does not support output mode.')

        # Only print these warnings and notes once; don't print for default FLASH/PSRAM function
        if (not self.assigned_functions and function != 'FLASH/PSRAM') or self.assigned_functions == ['FLASH/PSRAM']:
            # Strapping pin notes
            if self.strapping:
                logger.warn(
                    f'Pin {self.pin} is reserved for strapping. Please use with caution! '
                    f'Strapping function: {self.strapping}'
                )

            # Notes about pull-up/down resistors
            if self.at_reset == 'PUP':
                logger.note(f'Pin {self.pin} has an internal pull-up resistor enabled at reset.')
            elif self.at_reset == 'PDOWN':
                logger.note(f'Pin {self.pin} has an internal pull-down resistor enabled at reset.')

            # Check for debug functions
            if function not in DEBUG_FUCTIONS and self.is_debug_pin:
                logger.warn(f'Pin {self.pin} is reserved for JTAG debugging or USB. Please use with caution!')
            # Check for serial functions
            if function not in SERIAL_FUCTIONS and self.is_serial_pin:
                logger.warn(f'Pin {self.pin} is reserved for serial debug/programming. Please use with caution!')

        self.assigned_functions.append(function)
