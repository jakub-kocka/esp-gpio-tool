# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import click

from esp_gpio_tool.gui import GUI
from esp_gpio_tool_cli import __version__


@click.command()
@click.version_option(__version__)
def main() -> None:
    GUI()


if __name__ == '__main__':
    main()
