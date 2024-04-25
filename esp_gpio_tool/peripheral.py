# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from typing import Any


class BasePeripheral:
    count: int
    assigned_pins: dict[int, list[str]]  # e.g. {1: [ADC1_CH1, ADC1_CH2... ], 2: [ADC2_CH1, ADC2_CH2...}
    any_pins: dict[int, list[str]]

    def __init__(self, count: int, assigned_pins: list[str] = None, any_pin: list[str] = None, **kwargs: Any) -> None:
        # number of peripheral instances
        self.count = count

        # wildcard generation settings
        self.start_cnt = kwargs.get('start_cnt', 0)
        # names of instances, by default use counter from `start_cnt` to `count`
        self.instances = kwargs.get('instances', range(self.start_cnt, self.count + self.start_cnt))
        # keyword to replace in wildcard pins
        self._replace_keyword = kwargs.get('_replace_keyword', 'count')

        # convert wildcard pins to actual pins
        self.assigned_pins = self.unwrap_pins(assigned_pins)
        self.any_pins = self.unwrap_pins(any_pin)

    def __str__(self) -> str:
        return f'{self.__class__.__name__}(assigned_pins={self.assigned_pins}, any_pins={self.any_pins})'

    def __repr__(self) -> str:
        return self.__str__()

    def unwrap_pins(self, pins: list[str] | None) -> dict[int, list[str]]:
        """Convert wildcard pins to actual pins, e.g. DAC_{count} -> {1: [DAC_1], 2: [DAC_2]]"""
        output: dict[int, list[str]] = {}
        if pins is not None:
            # prepare output dict with empty lists per peripheral instance
            output = {i: [] for i in self.instances}
            for pin in pins:
                if f'{{{self._replace_keyword}}}' in pin:
                    for i in self.instances:
                        # replace wildcard with counter of peripheral instance
                        output[i].append(pin.format(**{self._replace_keyword: str(i)}))
                else:
                    output[self.start_cnt].append(pin)
        return output


class ADC(BasePeripheral):
    def __init__(self, count: int, assigned_pins: list[str] = None, any_pin: list[str] = None, **kwargs: Any) -> None:
        super().__init__(count, assigned_pins, any_pin, start_cnt=1)
        self.channels = kwargs.get('channels', 10)
        self.unwrap_channels(self.channels)

    def unwrap_channels(self, channels: int) -> None:
        """Convert wildcard channels to actual channels, e.g. ADC1_CH{channel} -> {1: [ADC1_CH1, ADC1_CH2... ]}"""
        for instance in self.assigned_pins.keys():
            for pin in self.assigned_pins[instance]:
                if '{channel}' in pin:
                    # replace wildcard with all possible channels
                    self.assigned_pins[instance].remove(pin)
                    self.assigned_pins[instance].extend([pin.format(channel=str(i)) for i in range(channels)])


class DAC(BasePeripheral):
    def __init__(self, count: int, assigned_pins: list[str] = None, any_pin: list[str] = None, **kwargs: Any) -> None:
        super().__init__(count, assigned_pins, any_pin, start_cnt=1)


class SPI(BasePeripheral):
    def __init__(self, count: int, assigned_pins: list[str] = None, any_pin: list[str] = None, **kwargs: Any) -> None:
        super().__init__(count, assigned_pins, any_pin, instances=kwargs.get('subname'), _replace_keyword='subname')
