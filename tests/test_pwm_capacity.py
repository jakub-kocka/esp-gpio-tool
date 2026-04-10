# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""PWM output capacity counting and find_chips filtering."""

from esp_gpio_tool_cli.chip import ESP
from esp_gpio_tool_cli.chip import get_pwm_output_capacity


def test_esp32c3_ledc_only_six_outputs() -> None:
    esp = ESP('esp32c3')
    cap = get_pwm_output_capacity(esp)
    assert cap['ledc_pwm_outputs'] == 6
    assert cap['mcpwm_pwm_outputs'] == 0
    assert cap['max_independent_pwm_outputs'] == 6


def test_esp32s3_ledc_plus_mcpwm() -> None:
    esp = ESP('esp32s3')
    cap = get_pwm_output_capacity(esp)
    assert cap['ledc_pwm_outputs'] == 8
    assert cap['mcpwm_pwm_outputs'] == 12
    assert cap['max_independent_pwm_outputs'] == 20


def test_find_chips_excludes_c3_for_twelve_servos() -> None:
    # Same PWM gate as find_chips(min_independent_pwm_outputs=12)
    ok = []
    for name in ('esp32c3', 'esp32s3'):
        esp = ESP(name)
        cap = get_pwm_output_capacity(esp)
        if cap['max_independent_pwm_outputs'] >= 12:
            ok.append(name)
    assert 'esp32c3' not in ok
    assert 'esp32s3' in ok
