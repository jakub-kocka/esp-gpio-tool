# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import re
from typing import Any

from esp_gpio_tool_cli.pin import Pin


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
        self.instances: list[str] = kwargs.get(
            'instances', [str(i) for i in range(self.start_cnt, self.count + self.start_cnt)]
        )
        # keyword to replace in wildcard pins
        self._replace_keyword = kwargs.get('_replace_keyword', 'count')
        self.used = {i: False for i in self.instances}

        # convert wildcard pins to actual pins
        self._assigned_pins = self.unwrap_pins(assigned_pins)
        self._universal_pins = self.unwrap_pins(universal_pins)
        self.optional_pins = {}

        # peripheral modes in selected peripherals
        self.supported_modes: dict[str, list[str | int]] = {}  # {"HSPI": ["Single SPI, "Dual SPI", "Quad SPI"]}
        self.mode: dict[str, str | int] = {}  # {"HSPI": "Single SPI", "VSPI": "Quad SPI"}
        self.mode_label: str | None = None  # Used only if mode is not self descriptive enough (for GUI mostly)

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

    def use(self, function: str, pin: Pin) -> str | None:
        """Check the pin if it can be used for this function and mark peripheral as used"""
        for instance in self.instances:
            if function in self.all_pins.get(instance, []):
                self.used[instance] = True
                return self.check_pin_function(instance, function, pin)
        raise ValueError(f'Function {function} not found in peripheral {self.name}.')

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> str | None:  # pylint: disable=useless-return
        """Check if the pin supports the function and if it can be used as input/output"""
        if function in self.assigned_pins.get(instance, []):
            if function not in pin.functions:
                raise ValueError(f'Pin {pin.pin} does not support function {function}.')
        # TODO add check for input/output capabilities of the pin
        return None  # return was forced by mypy, so we need to disable pylint check

    def required_pins(self, instance: str) -> list[str]:
        """Return all required pins for a peripheral instance"""
        if instance not in self.instances:
            raise ValueError(f'Instance {instance} not found.')
        return list(set(self.filtered_pins.get(instance, [])) - set(self.optional_pins.get(instance, [])))

    def unwrap_pins(self, pins: list[str] | None) -> dict[str, list[str]]:
        """Convert wildcard pins to actual pins, e.g.
        - DAC_{count} -> {1: [DAC_1], 2: [DAC_2]]
        -{subname}_PCLK -> {LCD: [LCD_PCLK], CAM: [CAM_PCLK]]
        """
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
        supported_modes = [str(i) for i in self.supported_modes.get(instance, [])]
        mode = str(mode)
        if mode not in supported_modes:
            raise ValueError(
                f'Mode {mode} is not supported for {self.name} {instance}. '
                f'Supported modes: {self.supported_modes[instance]}'
            )
        self.mode[instance] = mode


class ADC(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, start_cnt=1)
        channels = kwargs.get('channels', 10)
        if isinstance(channels, int):
            self.channels = {i: channels for i in self.instances}
        else:
            self.channels = channels
        self.unwrap_channels(self.channels, self._assigned_pins)
        self.optional_pins = self.assigned_pins  # all pins are optional

    def unwrap_channels(self, channels: dict[str, int], pins: dict[str, list[str]]) -> dict[str, list[str]]:
        """Convert wildcard channels to actual channels, e.g.
        - ADC1_CH{channel} -> {1: [ADC1_CH1, ADC1_CH2... ]}
        """
        for instance in self.assigned_pins.keys():
            for pin in self.assigned_pins[instance]:
                if '{channel}' not in pin:
                    continue
                # replace wildcard with all possible channels
                self._assigned_pins[instance].remove(pin)
                self._assigned_pins[instance].extend([pin.format(channel=str(i)) for i in range(channels[instance])])
        return pins


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
        modes: list | dict = kwargs.get('modes', [])
        # modes can be set in list format if same for all the sub-peripherals or in dict to specify exactly
        if isinstance(modes, list):
            self.supported_modes = {i: modes for i in self.instances}
        elif isinstance(modes, dict):
            self.supported_modes = modes
        self.mode = {i: 'Single SPI' for i in self.instances}

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        pins = {}
        for instance in self.instances:
            if self.mode[instance] in ['Single SPI', 'Dual SPI']:
                pins[instance] = ['SPICS0', 'SPICS1', 'SPICLK', 'SPIQ', 'SPID']
            elif self.mode[instance] in ['Quad SPI', 'QPI']:
                pins[instance] = list(
                    filter(
                        lambda x: not (x.endswith(('DQS', 'IO4', 'IO5', 'IO6', 'IO7'))), self._assigned_pins[instance]
                    )
                )
            elif self.mode[instance] in ['Octal SPI', 'OPI']:
                pins[instance] = self._assigned_pins[instance]
        return pins

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> str | None:
        """Check if the pin supports the function and if it can be used as input/output"""
        # Pin assignment can be changed to any pin with GPIO matrix so ignore checks here
        try:
            return super().check_pin_function(instance, function, pin)
        except ValueError:
            return (
                f"Note: {function} of {instance} was assigned to it's non-default pin using GPIO matrix, "
                'which will lead to slower transfer speeds and clock frequencies only up to 40 MHz.'
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

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> str | None:  # pylint: disable=useless-return
        if function.endswith('_CLK'):
            if not any(fun.startswith('CLK_OUT') for fun in pin.functions):
                raise ValueError(f'Pin {pin.pin} does not support CLK_OUT, which is required for {function}.')
        return None  # return was forced by mypy, so we need to disable pylint check


class TOUCH(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.optional_pins = self.assigned_pins  # all pins are optional


class UART(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins)
        self.optional_pins = self.unwrap_pins(['U{count}CTS', 'U{count}RTS'])
        self.common_prefix = r'U\d.'
        # TODO print warning if 0 instance is used? probably on PIN side or make UART0 turned on by default?

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> str | None:
        """Check if the pin supports the function and if it can be used as input/output"""
        # Pin assignment can be changed to any pin with GPIO matrix so ignore checks here
        try:
            return super().check_pin_function(instance, function, pin)
        except ValueError:
            return (
                f"Note: {function} of {instance} was assigned to it's non-default pin using GPIO matrix. "
                'It is recomanded to use pins from IO MUX if you need very high UART baud rates (over 40 MHz).'
            )


class SDIO(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.common_prefix = 'SD'
        self.supported_modes = kwargs.get('data_width', {str(i): [1] for i in self.instances})
        self.mode = {str(i): 1 for i in self.instances}
        self.mode_label = 'Data width'
        self._assigned_pins = self._unwrap_data_pins()

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        """Dynamic getter for assigned pins, based on data width of the peripheral instance"""
        pins = {}
        for instance in self.instances:
            width: int = int(self.mode.get(instance, 0)) - 1
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

    def set_mode(self, instance: str, mode: str) -> None:
        super().set_mode(instance, mode)
        self.mode[instance] = int(mode)


class SDMMC(BasePeripheral):
    """SD/MMC card peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, start_cnt=1, **kwargs)
        self.common_prefix = 'SDHOST'
        self.supported_modes = kwargs.get('data_width', {str(i): [1] for i in self.instances})
        self.mode = {str(i): 1 for i in self.instances}
        self.mode_label = 'Data width'
        self._universal_pins = self._unwrap_data_pins(self._universal_pins)
        if self._assigned_pins:
            self._assigned_pins = self._unwrap_data_pins(self._assigned_pins)
        self.optional_pins = self.universal_pins

    @property
    def universal_pins(self) -> dict[str, list[str]]:
        """Dynamic getter for universal pins, based on data width of the peripheral instance"""
        pins = {}
        for instance in self.instances:
            width: int = int(self.mode.get(instance, 0)) - 1
            regex = re.compile(rf'.+(CDATA_\d[0-{width}]|CCLK|CCMD|CARD|STROBE|RST|SDIO).*')
            pins[instance] = [pin for pin in self._universal_pins[instance] if regex.match(pin)]
        return pins

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        """Dynamic getter for assigned pins, based on data width of the peripheral instance"""
        pins = {}
        if self._assigned_pins:
            for instance in self.instances:
                width: int = int(self.mode.get(instance, 0)) - 1
                regex = re.compile(rf'.+(CDATA_\d[0-{width}]|CCLK|CCMD|CARD|STROBE|RST|SDIO).*')
                pins[instance] = [pin for pin in self._assigned_pins[instance] if regex.match(pin)]
        return pins

    def _unwrap_data_pins(self, orig_pins: dict[str, list[str]]) -> dict[str, list[str]]:
        pins: dict[str, list[str]] = {}
        for instance in self.instances:
            width = int(max(self.supported_modes.get(instance, [1])))
            pins[instance] = []
            for pin in orig_pins[instance]:
                if '{data_width}' not in pin:
                    pins[instance].append(pin)
                    continue
                # replace wildcard with all possible channels
                pins[instance].extend([pin.format(data_width=str(i)) for i in range(width)])
        return pins

    def set_mode(self, instance: str, mode: str) -> None:
        super().set_mode(instance, mode)
        self.mode[instance] = int(mode)


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
        self._universal_pins = self.unwrap_channels(kwargs.get('channels', None), self._universal_pins)
        self.optional_pins = self.universal_pins  # all pins are optional

    def unwrap_channels(self, channels: int, pins: dict[str, list[str]]) -> dict[str, list[str]]:
        """Convert wildcard channels to actual channels"""
        output: dict[str, list[str]] = {}
        if channels:
            for instance in pins.keys():
                output[instance] = []
                for pin in pins[instance]:
                    if '{channel}' not in pin:
                        output[instance].append(pin)
                    # replace wildcard with all possible channels
                    output[instance].extend([pin.format(channel=str(i)) for i in range(channels)])
            return output
        return pins


class PCNT(BasePeripheral):
    """Pulse Counter peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self._universal_pins = self.unwrap_channels(kwargs.get('channels', None), self._universal_pins)

    def unwrap_channels(self, channels: int, pins: dict[str, list[str]]) -> dict[str, list[str]]:
        """Convert wildcard channels to actual channels"""
        output: dict[str, list[str]] = {}
        if channels:
            for instance in pins.keys():
                output[instance] = []
                for pin in pins[instance]:
                    if '{channel}' not in pin:
                        output[instance].append(pin)
                    # replace wildcard with all possible channels
                    output[instance].extend([pin.format(channel=str(i)) for i in range(channels)])
            return output
        return pins


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
            pins.append('CLK_OUT')
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

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> str | None:
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
        return super().check_pin_function(instance, function, pin)


class CLKOUT(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, start_cnt=1, **kwargs)
        self.common_prefix = 'CLK_OUT'
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
        self.common_prefix = 'XTAL_32K_'


class USBOTG(BasePeripheral):
    """USB OTG peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.common_prefix = r'USB_OTG'


class USBSERIALJTAG(BasePeripheral):
    """USB Serial/JTAG peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.common_prefix = r'USB(?!_OTG).'


class LCDCAM(BasePeripheral):
    """LCD and Camera Controller peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(
            count, assigned_pins, universal_pins, instances=kwargs.get('subname'), _replace_keyword='subname'
        )
        self.common_prefix = r'LCD|CAM'
        # modes can be set in list format if same for all the sub-peripherals or in dict to specify exactly
        modes: list | dict = kwargs.get('modes', [])
        if isinstance(modes, list):
            self.supported_modes = {i: modes for i in self.instances}
        elif isinstance(modes, dict):
            self.supported_modes = modes
        self.mode = {i: self.supported_modes[i][0] for i in self.instances}
        self.unwrap_channels(kwargs.get('channels', 16), self._universal_pins)

    def unwrap_pins(self, pins: list[str] | None) -> dict[str, list[str]]:
        """Convert wildcard pins to actual pins, e.g. {subname}_PCLK -> {LCD: [LCD_PCLK], CAM: [CAM_PCLK]]"""
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
                    for instance in self.instances:
                        if instance in pin:
                            output[str(instance)].append(pin)
        return output

    def unwrap_channels(self, channels: int, pins: dict[str, list[str]]) -> dict[str, list[str]]:
        """Convert wildcard channels to actual channels, e.g.
        {subname}_DATA{{channel}} -> {LCD: [LCD_DATA0, LCD_DATA1... ]}
        """
        for instance, instance_val in self.universal_pins.items():
            for pin in instance_val:
                if '{channel}' not in pin:
                    continue
                # replace wildcard with all possible channels
                self._universal_pins[instance].remove(pin)
                self._universal_pins[instance].extend([pin.format(channel=str(i)) for i in range(channels)])
        return pins

    # TODO Pin OUT/IN based on the operation mode

    @property
    def universal_pins(self) -> dict[str, list[str]]:
        pins = {}
        for instance in self.instances:
            if '8 bit' in str(self.mode[instance]):
                pins[instance] = list(
                    filter(
                        lambda x: not x.endswith(tuple(str(x) for x in range(8, 16))),
                        self._universal_pins[instance],
                    )
                )
            elif '16 bit' in str(self.mode[instance]):
                pins[instance] = self._universal_pins[instance]
        return pins
