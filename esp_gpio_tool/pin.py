# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass
from dataclasses import field


@dataclass
class Pin:
    pin: int
    power_domain: str
    is_input: bool = True
    is_output: bool = True
    strapping: str | None = None
    functions: list[str] = field(default_factory=list)
    reserved: list[str] = field(default_factory=list)
    assigned_function: str | None = None

    @property
    def used(self) -> bool:
        return self.assigned_function is not None

    def __str__(self) -> str:
        return f'Pin({self.pin}, {self.functions}), assigned_function={self.assigned_function}'

    def __repr__(self) -> str:
        return str(self)

    def assign_function(self, function: str) -> list[str]:
        output = []
        if self.used:
            raise ValueError(f'Pin {self.pin} already assigned to {self.assigned_function}')
        if function == 'INPUT' and not self.is_input:
            raise ValueError(f'Pin {self.pin} does not support input')
        if function == 'OUTPUT' and not self.is_output:
            raise ValueError(f'Pin {self.pin} does not support output')
        self.assigned_function = function
        if self.strapping:
            output.append(
                f'Warning: Pin {self.pin} is reserved for strapping, use with caution! '
                f'Strapping function: {self.strapping}'
            )
        return output
