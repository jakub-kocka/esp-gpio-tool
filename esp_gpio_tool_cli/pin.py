# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from dataclasses import field

from esp_gpio_tool_cli.logger import Logger

logger = Logger()


@dataclass
class Pin:
    pin: int
    power_domain: str
    is_input: bool = True
    is_output: bool = True
    strapping: str | None = None
    functions: list[str] = field(default_factory=list)
    at_reset: str | None = None
    assigned_function: list[str] = field(default_factory=list)

    @property
    def used(self) -> bool:
        return bool(self.assigned_function)

    def __str__(self) -> str:
        return f'GPIO{self.pin} - {self.power_domain}'

    def __repr__(self) -> str:
        return str(self)

    def assign_function(self, function: str) -> None:
        # Check for pin compatibility
        if function == 'INPUT' and not self.is_input:
            raise ValueError(f'Pin {self.pin} does not support input mode.')
        if function == 'OUTPUT' and not self.is_output:
            raise ValueError(f'Pin {self.pin} does not support output mode.')

        # Only print these warnings and notes once; don't print for default Flash/PSRAM function
        if (not self.assigned_function and function != 'Flash/PSRAM') or self.assigned_function == ['Flash/PSRAM']:
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

        self.assigned_function.append(function)
