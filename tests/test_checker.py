# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import pytest

from esp_gpio_tool_cli.checker import run_check
from esp_gpio_tool_cli.chip import SUPPORTED_CHIPS
from esp_gpio_tool_cli.logger import Logger

Logger().use_unicode(False)


def run(config: str) -> list[str]:
    """Run the checker with the given config and log returned file"""
    out = run_check(config)
    # newline to separate the output from test name
    print('\n' + '\n'.join(out))
    return out


def test_missing_chip() -> None:
    config = """
    36: ADC1_CH0
    37: ADC1_CH1
    """
    out = run(config)
    assert 'Warning: Chip name not found in input file. Assuming ESP32.' in out


def test_invalid_chip() -> None:
    config = """
    chip: foo
    0: ADC1_CH0
    1: ADC1_CH1
    """
    with pytest.raises(SystemExit) as exc_info:
        run(config)
    assert exc_info.value.args[0] == f"Error: Invalid chip: 'foo'. Supported chips: {SUPPORTED_CHIPS}."


@pytest.mark.parametrize('chip', SUPPORTED_CHIPS)
def test_duplicate_pin(chip: str) -> None:
    config = f"""
    chip: {chip}
    0: ADC1_CH0
    0: TOUCH1
    """
    with pytest.raises(SystemExit) as exc_info:
        run(config)
    assert exc_info.value.args[0] == "Error: Invalid format: Duplicate '0' key found in YAML."


def test_valid_config() -> None:
    config = """
    chip: esp32
    36: ADC1_CH0
    37: ADC1_CH1
    """
    result = run(config)
    assert 'All checks passed.' in result


def test_valid_config_multiple_functions() -> None:
    config = """
    chip: esp32
    36: ADC1_CH0
    3: [LEDC_SIG_OUT0, LEDC_SIG_OUT1, RMT_SIG_IN0]
    """
    result = run(config)
    assert (
        'Warning: Pin 3 has been used multiple times, reusing pins is not recommended. '
        'Assigned functions: LEDC_SIG_OUT0, LEDC_SIG_OUT1, RMT_SIG_IN0' in result
    )


def test_invalid_pin_format() -> None:
    config = """
    chip: esp32
    0: INVALID_FUNCTION
    """
    out = run(config)
    assert 'Error: Function INVALID_FUNCTION not found in peripherals for esp32.' in out


def test_wrong_pin_function() -> None:
    config = """
    chip: esp32
    0: ADC1_CH0
    """
    out = run(config)
    assert 'Error: Pin 0 does not support function ADC1_CH0.' in out


def test_nonexisting_pin() -> None:
    config = """
    chip: esp32
    24: ADC1_CH0
    """
    out = run(config)
    assert 'Error: Pin 24 not found for esp32.' in out


def test_wrong_function_correct_prefix() -> None:
    config = """
    chip: esp32
    36: ADC1_FOO
    """
    out = run(config)
    assert 'Error: Function ADC1_FOO not found in peripheral ADC.' in out


def test_output_notsupported() -> None:
    config = """
    chip: esp32
    36: OUTPUT
    """
    out = run(config)
    assert 'Error: Pin 36 does not support output mode.' in out


def test_I2S_clk() -> None:
    config = """
    chip: esp32
    21: I2S0_CLK
    22: I2S0_WS
    23: I2S0_SD
    """
    out = run(config)
    assert 'Error: Pin 21 does not support CLK_OUT, which is required for I2S0_CLK.' in out


def test_SPI_modes() -> None:
    config = """
    chip: esp32

    peripheral:
        SPI:
            HSPI: QSPI

    2:  HSPIWP
    4:  HSPIHD
    12: HSPIQ
    13: HSPID
    14: HSPICLK
    15: HSPICS0
    """
    out = run(config)
    assert 'Error' not in out


@pytest.mark.parametrize('mode', ['1', '4'])
def test_SDIO_mode(mode: str) -> None:
    config = f"""
    chip: esp32

    peripheral:
        SDIO:
            0: {mode}

    6:  SDIO0_CLK
    7:  SDIO0_DATA0
    8:  SDIO0_DATA1
    9:  SDIO0_DATA2
    10: SDIO0_DATA3
    11: SDIO0_CMD
    """
    out = '\n'.join(run(config))
    assert 'Error' not in out


def test_SDIO_mode_missing_pins() -> None:
    config = """
    chip: esp32

    peripheral:
        SDIO:
            0: 4

    6:  SDIO0_CLK
    7:  SDIO0_DATA0
    11: SDIO0_CMD
    """
    out = '\n'.join(run(config))
    for pin in ['SDIO0_DATA1', 'SDIO0_DATA2', 'SDIO0_DATA3']:
        assert f'Error: Required function {pin} from peripheral SDIO is not assigned to any pin.' in out


def test_soc_not_found() -> None:
    config = """
    chip: esp32
    soc: foo
    """
    with pytest.raises(SystemExit) as exc_info:
        run(config)
    assert 'Error: SoC "foo" is not supported variant of esp32. Supported SoCs: ' in exc_info.value.args[0]


@pytest.mark.parametrize('soc, nc_pins', [('ESP32-PICO-V3', [16, 17, 18, 23]), ('ESP32-D0WD-V3', [20])])
def test_soc_filter_gpios(soc: str, nc_pins: list[int]) -> None:
    config = f"""
    chip: esp32
    soc: {soc}
    """
    for pin in nc_pins:
        config += f'\n    {pin}: ADC1_CH0'
    out = run(config)
    for pin in nc_pins:
        assert f'Error: Pin {pin} not found for esp32({soc}).' in out


def test_flash_pin_reuse() -> None:
    config = """
    chip: esp32
    soc: ESP32-PICO-V3
    6: U1CTS
    """
    out = run(config)
    assert (
        'Warning: Pin 6 has been used multiple times, reusing pins is not recommended. '
        'Assigned functions: FLASH/PSRAM, U1CTS' in out
    )


def test_sdmmc() -> None:
    config = """
    chip: esp32s3
    peripheral:
        SDMMC:
            1: 4
    0: SDHOST_CCLK_1
    1: SDHOST_CCMD_1
    2: SDHOST_CDATA_10
    3: SDHOST_CDATA_11
    4: SDHOST_CDATA_12
    5: SDHOST_CDATA_13
    """
    out = run(config)
    assert 'Error' not in ''.join(out)
    for idx, pin in enumerate(['CCMD_1', 'CDATA_10', 'CDATA_11', 'CDATA_12', 'CDATA_13']):
        assert f'Note: Function SDHOST_{pin} requires 10k pull-up resistor on pin GPIO{idx+1}.' in out


def test_reuse_debug_pins() -> None:
    config = """
    chip: esp32s3
    19: OUTPUT  # USB_D+
    39: OUTPUT  # MTCK (JTAG)
    43: OUTPUT  # U0TXD (Serial)
    """
    out = '\n'.join(run(config))
    assert 'Error' not in out
    assert 'Warning: Pin 19 is reserved for JTAG debugging or USB.' in out
    assert 'Warning: Pin 39 is reserved for JTAG debugging or USB.' in out
    assert 'Warning: Pin 43 is reserved for serial debug/programming.' in out
