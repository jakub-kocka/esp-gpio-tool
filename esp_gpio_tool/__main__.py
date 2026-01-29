# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import rich_click as click

from esp_gpio_tool.gui import GUI
from esp_gpio_tool_cli import __version__
from esp_gpio_tool_cli.logger import Logger


@click.command()
@click.version_option(__version__)
@click.option('--no-unicode', is_flag=True, help='Disable Unicode characters in the output.')
def main(no_unicode: bool = False) -> None:
    """ESP GPIO Tool GUI"""
    Logger().use_unicode(not no_unicode)
    GUI()


if __name__ == '__main__':
    main()
