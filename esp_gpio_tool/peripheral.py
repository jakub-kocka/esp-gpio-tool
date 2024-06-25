# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import re
from typing import Any

from esp_gpio_tool.pin import Pin


class BasePeripheral:
    count: int
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
        self.instances = kwargs.get('instances', [str(i) for i in range(self.start_cnt, self.count + self.start_cnt)])
        # keyword to replace in wildcard pins
        self._replace_keyword = kwargs.get('_replace_keyword', 'count')
        self.used = {i: False for i in self.instances}

        # convert wildcard pins to actual pins
        self._assigned_pins = self.unwrap_pins(assigned_pins)
        self._universal_pins = self.unwrap_pins(universal_pins)
        self.optional_pins = {}

        # peripheral modes in selected peripherals
        self.supported_modes: dict[str, list[str | int]] = {}  # {"HSPI": ["Standard SPI", "QSPI"]}
        self.mode: dict[str, str | int] = {}  # {"HSPI": "Standard SPI", "VSPI": "QSPI"}

    def __str__(self) -> str:
        return f'{self.name}(assigned_pins={self.assigned_pins}, universal_pins={self.universal_pins})'

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        return self._assigned_pins

    @property
    def universal_pins(self) -> dict[str, list[str]]:
        return self._universal_pins

    @property
    def all_pins(self) -> dict[str, list[str]]:
        """Return all assigned and universal pins"""
        return {i: self._assigned_pins.get(i, []) + self._universal_pins.get(i, []) for i in self.instances}

    @property
    def filtered_pins(self) -> dict[str, list[str]]:
        """Return all assigned and universal pins, filtered by selected mode"""
        return {i: self.assigned_pins.get(i, []) + self.universal_pins.get(i, []) for i in self.instances}

    def use(self, function: str, pin: Pin) -> None:
        """Check the pin if it can be used for this function and mark peripheral as used"""
        for instance in self.instances:
            if function in self.all_pins.get(instance, []):
                self.used[instance] = True
                self.check_pin_function(instance, function, pin)
                return
        raise ValueError(f'Function {function} not found in peripheral {self.name}.')

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        """Check if the pin supports the function and if it can be used as input/output"""
        if function in self.assigned_pins.get(instance, []):
            if function not in pin.functions:
                raise ValueError(f'Pin {pin.pin} does not support function {function}.')
        # TODO add check for input/output capabilities of the pin

    def required_pins(self, instance: str) -> list[str]:
        """Return all required pins for a peripheral instance"""
        if instance not in self.instances:
            raise ValueError(f'Instance {instance} not found.')
        return list(set(self.filtered_pins.get(instance, [])) - set(self.optional_pins.get(instance, [])))

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
                    output[str(self.start_cnt)].append(pin)
        return output

    def set_mode(self, instance: str, mode: str) -> None:
        """Set mode of interface communication"""
        if instance not in self.instances:
            raise ValueError(f'Instance {instance} not found. Supported instances: {self.instances}')
        if mode not in self.supported_modes.get(instance, []):
            raise ValueError(
                f'Mode {mode} is not supported for {self.name} {instance}. Supported modes: {self.supported_modes}'
            )
        self.mode[instance] = mode


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
                if '{channel}' not in pin:
                    continue
                # replace wildcard with all possible channels
                self._assigned_pins[instance].remove(pin)
                self._assigned_pins[instance].extend([pin.format(channel=str(i)) for i in range(channels)])


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
        self.common_prefix = r'.?SPI'
        self.supported_modes = {i: kwargs.get('modes', []) for i in self.instances}
        self.mode = {i: 'Standard SPI' for i in self.instances}

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        pins = {}
        for instance in self.instances:
            if self.mode[instance] == 'Standard SPI':
                pins[instance] = list(filter(lambda x: not (x.endswith('HD') or x.endswith('WP')), self._assigned_pins))
            elif self.mode[instance] == 'QSPI':
                pins[instance] = self._assigned_pins[instance]
        return pins

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        """Check if the pin supports the function and if it can be used as input/output"""
        # Pin assignment can be changed to any pin with GPIO matrix so ignore checks here
        try:
            super().check_pin_function(instance, function, pin)
        except ValueError as exc:
            raise ValueError(
                f"Note: {function} of {instance} was assigned to it's non-default pin using GPIO matrix, "
                'which will lead to slower transfer speeds and clock frequencies only up to 40 MHz.'
            ) from exc


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
                raise ValueError(f'Pin {pin.pin} does not support CLK_OUT, which is required for {function}.')


class TOUCH(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins)
        self.optional_pins = self.assigned_pins  # all pins are optional


class UART(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins)
        self.optional_pins = self.unwrap_pins(['U{count}CTS', 'U{count}RTS'])
        self.common_prefix = r'U.'
        # TODO print warning if 0 instance is used? probably on PIN side or make UART0 turned on by default?

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        """Check if the pin supports the function and if it can be used as input/output"""
        # Pin assignment can be changed to any pin with GPIO matrix so ignore checks here
        try:
            super().check_pin_function(instance, function, pin)
        except ValueError as exc:
            raise ValueError(
                f"Note: {function} of {instance} was assigned to it's non-default pin using GPIO matrix. "
                'It is recomanded to use pins from IO MUX if you need very high UART baud rates (over 40 MHz).'
            ) from exc


class SDIO(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.common_prefix = 'SD'
        self.supported_modes = kwargs.get('data_width', {str(i): 1 for i in self.instances})
        self.mode = {str(i): 1 for i in self.instances}
        self._assigned_pins = self._unwrap_data_pins()

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        """Dynamic getter for assigned pins, based on data width of the peripheral instance"""
        pins = {}
        for instance in self.instances:
            width = self.mode.get(instance)
            regex = re.compile(rf'[A-Z]{{2}}\d_(CLK|CMD|DATA[0-{width}])')
            pins[instance] = [pin for pin in self._assigned_pins[instance] if regex.match(pin)]
        return pins

    def _unwrap_data_pins(self) -> dict[str, list[str]]:
        assigned_pins: dict[str, list[str]] = {}
        for instance in self.instances:
            width = int(max(self.supported_modes.get(instance, [1])))
            assigned_pins[instance] = []
            for pin in self._assigned_pins[instance]:
                if '{data_width}' not in pin:
                    assigned_pins[instance].append(pin)
                    continue
                # replace wildcard with all possible channels
                assigned_pins[instance].extend([pin.format(data_width=str(i)) for i in range(width)])
        return assigned_pins


class SDMMC(SDIO):
    """SD/MMC card peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.optional_pins = self.universal_pins
        self.common_prefix = 'HS'


class RMT(BasePeripheral):
    """Remote Control Transceiver peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.optional_pins = self.universal_pins  # all pins are optional, based on usage


class LEDC(BasePeripheral):
    """LED PWM peripheral"""


class MCPWM(BasePeripheral):
    """Motor Control PWM peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.optional_pins = self.universal_pins  # all pins are optional


class PCNT(BasePeripheral):
    """Pulse Counter peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.unwrap_channels(kwargs.get('channels', 2))

    def unwrap_channels(self, channels: int) -> None:
        """Convert wildcard channels to actual channels"""
        out: dict[str, list[str]] = {}
        for instance in self._universal_pins.keys():
            out[instance] = []
            for pin in self._universal_pins[instance]:
                if '{channel}' not in pin:
                    out[instance].append(pin)
                # replace wildcard with all possible channels
                out[instance].extend([pin.format(channel=str(i)) for i in range(channels)])
        self._universal_pins = out


class JTAG(BasePeripheral):
    """JTAG peripheral"""


class EMAC(BasePeripheral):
    """Ethernet MAC peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.supported_modes = {'0': kwargs.get('modes', [])}
        self.mode = {'0': 'RMII external CLK'}

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        # shared pins for RMII and MII
        pins = ['TX_CLK', 'TX_EN', 'TXD0', 'TXD1', 'RX_DV', 'RXD0', 'RXD1']
        if self.mode['0'] == 'RMII internal CLK':
            pins.append('EMAC_CLK_OUT')
        elif self.mode['0'] == 'MII':
            # additional pins needed for MII
            pins.extend(['RX_CLK', 'TXD2', 'TXD3', 'RX_ER', 'RXD2', 'RXD3', 'TX_ER'])
        # sort pins so similar pins are after each other; maily for additional TX and RX in MII
        pins.sort()
        # add prefixes to the pins, for better naming in the config
        return {'0': [f'EMAC_{i}' for i in pins]}

    @property
    def universal_pins(self) -> dict[str, list[str]]:
        pins = ['EMAC_MDC', 'EMAC_MDI', 'EMAC_MDO', 'EMAC_CRS']
        if self.mode['0'] == 'MII':
            pins.append('EMAC_COL')
        return {'0': pins}

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        if function == 'EMAC_CLK_OUT':
            # Note: CLK_OUT1 is experimental and on ESP32 is shared with RX_CLK signal on the same GPIO
            if not any(fun in ['CLK_OUT1', 'EMAC_CLK_OUT', 'EMAC_CLK_OUT_180'] for fun in pin.functions):
                raise ValueError(f'Pin {pin.pin} does not support clock out, which is required for {function}.')
        elif function in ['EMAC_MDC', 'EMAC_MDO', 'EMAC_CRS', 'EMAC_COL']:
            # check if GPIO supports output
            if not pin.is_output:
                raise ValueError(f'Pin {pin.pin} does not support output, which is required for {function}.')
        elif function in ['EMAC_MDI']:
            if not pin.is_output:
                raise ValueError(f'Pin {pin.pin} does not support input, which is required for {function}.')
        else:
            super().check_pin_function(instance, function, pin)


class CLKOUT(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.optional_pins = self.assigned_pins  # all pins are optional


class RTC(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.optional_pins = self.assigned_pins  # all pins are optional


class TWAI(BasePeripheral):
    """Two-Wire Automotive Interface peripheral (CAN)"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.optional_pins = {i: ['twai_bus_off_on', 'twai_clkout'] for i in self.instances}


class XTAL32K(BasePeripheral):
    """32 kHz crystal oscillator peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        # based on usage, pins can be optional
        self.optional_pins = self.assigned_pins  # all pins are optional
