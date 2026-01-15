# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
- Prepare HACS packaging and metadata
- Add final `codeowners` and repository URLs

### Added
- Debug logs for diagnostics calls (`diagnostics.py`)
- Debug logs for button press actions (`button.py`)
- Debug logs for reboot/reset commands in gateway (`boiler_gateway.py`)
- Comprehensive debug logging documentation in BUILD.md, DESIGN.md, and CLAUDE.md

## [0.1.0] - 2026-01-07
### Added
- Initial integration implementation: Modbus protocol wrapper, BoilerGateway, DataUpdateCoordinator
- Entity platforms: `sensor`, `binary_sensor`, `number`, `switch`
- Config flow for serial port and slave ID selection
- Integration-level services: `reboot_adapter`, `reset_boiler_errors`
- Unit and integration tests with ~92% code coverage
- HACS metadata: `manifest.json`, `hacs.json`, `translations/strings.json`, `README.md`

### Fixed
- Various test and mocking improvements for CI

