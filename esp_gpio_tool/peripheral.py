# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from typing import Any

from esp_gpio_tool.pin import Pin


class BasePeripheral:
    count: int
    assigned_pins: dict[str, list[str]]  # e.g. {1: [ADC1_CH1, ADC1_CH2... ], 2: [ADC2_CH1, ADC2_CH2...}
    universal_pins: dict[str, list[str]]
    optional_pins: dict[str, list[str]]
    common_prefix: str  # I2C1_SCL, I2C1_SDA -> I2C
    used: dict[str, bool]

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        self.common_prefix = self.name
        # number of peripheral instances
        self.count = count

        # wildcard generation settings
        self.start_cnt = kwargs.get('start_cnt', 0)
        # names of instances, by default use counter from `start_cnt` to `count`
        self.instances = kwargs.get('instances', range(self.start_cnt, self.count + self.start_cnt))
        # keyword to replace in wildcard pins
        self._replace_keyword = kwargs.get('_replace_keyword', 'count')
        self.used = {i: False for i in self.instances}

        # convert wildcard pins to actual pins
        self.assigned_pins = self.unwrap_pins(assigned_pins)
        self.universal_pins = self.unwrap_pins(universal_pins)
        self.optional_pins = {}

    def __str__(self) -> str:
        return f'{self.name}(assigned_pins={self.assigned_pins}, universal_pins={self.universal_pins})'

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def all_pins(self) -> dict[str, list[str]]:
        """Return all assigned and any pins"""
        return {i: self.assigned_pins.get(i, []) + self.universal_pins.get(i, []) for i in self.instances}

    def use(self, function: str, pin: Pin) -> None:
        """Check the pin if it can be used for this function and mark peripheral as used"""
        for instance in self.instances:
            if function in self.all_pins.get(instance, []):
                self.used[instance] = True
                self.check_pin_function(instance, function, pin)
                return
        raise ValueError(f'Function {function} not found in peripheral {self.name}')

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        """Check if the pin supports the function and if it can be used as input/output"""
        if function in self.assigned_pins.get(instance, []):
            if function not in pin.functions:
                raise ValueError(f'Pin {pin.pin} does not support function {function}')
        # TODO add check for input/output capabilities of the pin

    def required_pins(self, instance: str) -> list[str]:
        """Return all required pins for a peripheral instance"""
        if instance not in self.instances:
            raise ValueError(f'Instance {instance} not found')
        return list(set(self.all_pins.get(instance, [])) - set(self.optional_pins.get(instance, [])))

    def unwrap_pins(self, pins: list[str] | None) -> dict[str, list[str]]:
        """Convert wildcard pins to actual pins, e.g. DAC_{count} -> {1: [DAC_1], 2: [DAC_2]]"""
        output: dict[str, list[str]] = {}
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
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, start_cnt=1)
        self.channels = kwargs.get('channels', 10)
        self.unwrap_channels(self.channels)
        self.optional_pins = self.assigned_pins  # all pins are optional

    def unwrap_channels(self, channels: int) -> None:
        """Convert wildcard channels to actual channels, e.g. ADC1_CH{channel} -> {1: [ADC1_CH1, ADC1_CH2... ]}"""
        for instance in self.assigned_pins.keys():
            for pin in self.assigned_pins[instance]:
                if '{channel}' in pin:
                    # replace wildcard with all possible channels
                    self.assigned_pins[instance].remove(pin)
                    self.assigned_pins[instance].extend([pin.format(channel=str(i)) for i in range(channels)])


class DAC(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, start_cnt=1)
        self.optional_pins = self.assigned_pins  # all pins are optional


class SPI(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(
            count, assigned_pins, universal_pins, instances=kwargs.get('subname'), _replace_keyword='subname'
        )


class I2C(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins)


class I2S(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins)

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        if function.endswith('_CLK'):
            if not any(fun.startswith('CLK_OUT') for fun in pin.functions):
                raise ValueError(f'Pin {pin.pin} does not support CLK_OUT, which is required for {function}')


class TOUCH(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins)
        self.optional_pins = self.assigned_pins  # all pins are optional
