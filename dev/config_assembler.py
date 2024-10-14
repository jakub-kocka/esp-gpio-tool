#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
#
# This script is meant to generate "gpio" part of the target configuration file from excel "pin-table-helper" file.
#
# Usage: run this script with the "assemble" argument and provide path to the excel file
import click
import pandas as pd


def _functions_builder(file: pd.DataFrame) -> list[list[str]]:
    functions = []
    fnc_names = [
        'Analog  Function0',
        'Analog  Function1',
        'RTC_GPIO',
        'Digital Function0',
        'Digital Function2',
        'Digital Function3',
        'Digital Function4',
        'LP GPIO Function0',
        'LP GPIO Function1',
    ]
    for i, val in enumerate(file['Digital Function1']):
        pin_fncs = []
        for fnc in fnc_names:
            if file.get(fnc) is None:
                # There might be some columns missing in the excel file
                continue
            if file[fnc][i] == val:
                continue
            if not pd.isna(file[fnc][i]):
                pin_fncs.append(file[fnc][i])
        functions.append(pin_fncs)

    return functions


def _yaml_builder(
    gpios: pd.Series,
    power_domain: pd.Series,
    functions: list[list[str]],
    strapping: pd.Series,
    at_reset: pd.Series,
) -> None:
    """Print YAML-like format which can be used directly in the configuration file"""
    print('gpio:')
    for i, pin in enumerate(gpios):
        if pd.isna(pin):
            # lines with some note but empty pin number
            continue
        pin = pin.split('GPIO')[1]
        line = ''
        line += f'\t{pin}:\t{{ power_domain: {power_domain[i]}'

        line += f',\tfunctions: {functions[i]}'

        if not pd.isna(strapping[i]):
            line += f', strapping: "{strapping[i]}"'

        pull_res = None
        if 'wpu' in at_reset[i]:
            pull_res = 'PUP'
        elif 'wpd' in at_reset[i]:
            pull_res = 'PDOWN'

        line += f', at_reset: {pull_res}' if pull_res else ''

        line += ' }'

        print(line)


@click.group(no_args_is_help=True)
def main() -> None:
    pass


@main.command()
@click.argument('filepath', type=click.Path(exists=True), required=True)
def assemble(filepath: str) -> None:
    """Main function performing the assembly of the gpio section for the config file"""
    excel_file: pd.DataFrame = pd.read_excel(filepath, sheet_name='raw-data')

    gpios = excel_file['Digital Function1']
    power_domain = excel_file['Power']
    functions = _functions_builder(excel_file)
    strapping = excel_file['Strapping']
    at_reset = excel_file['At Reset']

    _yaml_builder(gpios, power_domain, functions, strapping, at_reset)


if __name__ == '__main__':
    main()
