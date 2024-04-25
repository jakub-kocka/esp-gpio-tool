# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0


class Pin:
    assigned_function: str | None = None
    number = 0
    input = True
    output = True
    strapping = None
    functions: list[str] = []

    @property
    def used(self) -> bool:
        return self.assigned_function is not None

    def __init__(
        self,
        pin: int,
        functions: list[str],
        is_input: bool = True,
        is_output: bool = True,
        strapping: str = None,
        reserved: list[str] = None,
    ) -> None:
        self.pin = pin
        self.functions = functions
        self.is_input = is_input
        self.is_output = is_output
        self.strapping = strapping
        self.reserved = reserved or []  # reserved functions of the pin for specific variants of chip, e.g. PSRAM

    def __str__(self) -> str:
        return f'Pin({self.pin}, {self.functions}), assigned_function={self.assigned_function}'

    def __repr__(self) -> str:
        return str(self)
