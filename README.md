<div align="center">
    <h1>ESP GPIO Tool</h1>
    <hr>
    <!-- Gitlab Badges -->
    <a href="https://gitlab.espressif.cn:6688/espressif/esp-gpio-tool/-/releases">
        <img alt="Latest Release" src="https://gitlab.espressif.cn:6688/espressif/esp-gpio-tool/-/badges/release.svg" />
    </a>
    <a href="https://gitlab.espressif.cn:6688/espressif/esp-gpio-tool/-/pipelines?scope=all&ref=master">
        <img alt="pipeline status" src="https://gitlab.espressif.cn:6688/espressif/esp-gpio-tool/badges/master/pipeline.svg?key_text=Master+Pipeline&key_width=100" />
    </a>
    <a href="https://gitlab.espressif.cn:6688/espressif/esp-gpio-tool/-/graphs/master/charts">
        <img alt="coverage report" src="https://gitlab.espressif.cn:6688/espressif/esp-gpio-tool/badges/master/coverage.svg?key_text=Test+Coverage&key_width=100" />
    </a>
    <hr>
</div>

**Welcome to the ESP GPIO Tool!**
This repository is a Python-based, open-source package that is used for developing applications with Espressif's SoCs.

It offers GPIO-related tools.

- **GPIO assignment checker**: Checks if used GPIOs are correctly assigned to peripherals.


---

- [Getting Started](#getting-started)
  - [Usage](#usage)
- [Documentation](#documentation)
- [CI/CD Overview](#cicd-overview)
  - [GitLab CI/CD](#gitlab-cicd)
  - [GitHub Actions](#github-actions)
- [CHANGELOG](#changelog)
- [License](#license)
- [Contributing](#contributing)

---

## Getting Started

### Usage

1. Install the Python package
   ```
   pip install esp-gpio-tool
   ```


---

## Documentation

TBD

---


## CI/CD Overview

### GitLab CI/CD

This project includes a basic GitLab CI configuration with the following jobs:

- **Pre-commit**: Executes checks identical to local pre-commit hooks.
- **Shared CI Danger**: A standard Espressif linting tool for merge requests.
- **Pytest**: Runs tests and coverage, integrated with the GitLab UI.
- **Pylint**: Lints code in accordance with Python best practices.


### GitHub Actions

- TBD

---

## CHANGELOG

- The [`CHANGELOG.md`](CHANGELOG.md) file.

## License

This document and the attached source code are released as Free Software under Apache License Version 2 or later. See the accompanying [LICENSE](LICENSE) file for a copy.

## Contributing

📘 If you are interested in contributing to this project, see the [project Contributing Guide](CONTRIBUTING.md).
