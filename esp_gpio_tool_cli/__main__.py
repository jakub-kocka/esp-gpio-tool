# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import click

from esp_gpio_tool_cli import __version__
from esp_gpio_tool_cli.checker import run_check


@click.group(no_args_is_help=True)
@click.version_option(__version__)
def main() -> None:
    pass


@main.command()
@click.argument('filename', type=click.Path(exists=True), required=True)
def check(filename: str) -> None:
    """Check the pin configuration from the given yaml file"""
    with open(filename, 'r', encoding='UTF-8') as file:
        user_input = file.read()
    output = run_check(user_input)
    for line in output:
        print(line)
    if 'All checks passed.' not in output:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
