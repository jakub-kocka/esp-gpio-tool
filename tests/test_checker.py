# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import pytest

from esp_gpio_tool_cli.checker import run_check
from esp_gpio_tool_cli.chip import SUPPORTED_CHIPS


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
    assert 'Warning: Pin 3 has been used multiple times, this may be a mistake, please be aware.' in result


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

    6 : SD0_CLK
    7:  SD0_DATA0
    8:  SD0_DATA1
    9:  SD0_DATA2
    10: SD0_DATA3
    11: SD0_CMD
    """
    out = '\n'.join(run(config))
    assert 'Error' not in out


def test_SDIO_mode_missing_pins() -> None:
    config = """
    chip: esp32

    peripheral:
        SDIO:
            0: 4

    6 : SD0_CLK
    7:  SD0_DATA0
    11: SD0_CMD
    """
    out = '\n'.join(run(config))
    for pin in ['SD0_DATA1', 'SD0_DATA2', 'SD0_DATA3']:
        assert f'Error: Required function {pin} from peripheral SDIO is not assigned to any pin.' in out
