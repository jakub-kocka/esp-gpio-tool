from esp_gpio_tool.__main__ import main


def test_main() -> None:
    assert 'ESP GPIO Tool' in main()
