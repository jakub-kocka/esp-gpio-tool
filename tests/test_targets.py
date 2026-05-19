# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from click.testing import CliRunner

from esp_gpio_tool_cli.__main__ import main
from esp_gpio_tool_cli.chip import SUPPORTED_CHIPS


def test_targets() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ['targets'])
    assert result.exit_code == 0
    for chip in SUPPORTED_CHIPS:
        assert chip in result.output
