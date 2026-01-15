# PR Checklist: Implement Remaining Items from IMPLEMENTATION_PLAN.md

This file maps the missing or partial items from `IMPLEMENTATION_PLAN.md` to concrete TODOs, file locations, test requirements, and estimated effort so a PR can be opened with a clear implementation plan.

**Summary of current state**
- Most core pieces implemented: Modbus wrapper, `BoilerGateway`, `DataUpdateCoordinator`, `config_flow`, basic entities, integration setup, diagnostics, and tests.
- Missing or partial items: `climate` entity, HA `button` entities for reboot/reset, full entity coverage (numbers/switches/buttons), centralized `RetryPolicy`, adapter-type sensor, and some planned advanced features (discovery, multi-register write optimization, MQTT bridge).  See detailed TODOs below.

---

**How to use this checklist**
- Implement each checked item in a dedicated branch and reference this checklist in the PR description.
- Update the checkboxes as sub-tasks are completed and add links to commits or tests.

---

## Mapped TODOs (Concrete tasks)

- [ ] Implement `Climate` entity (primary thermostat)
  - Files to add/modify:
    - [custom_components/ectocontrol_modbus_controller/entities/climate.py](custom_components/ectocontrol_modbus_controller/entities/climate.py#L1)
    - Wire into [custom_components/ectocontrol_modbus_controller/__init__.py](custom_components/ectocontrol_modbus_controller/__init__.py#L1) forward entry setups
  - Tests:
    - Add `tests/test_entities_climate.py` covering `current_temperature`, `target_temperature`, `hvac_action`, `set_hvac_mode`, and `set_temperature`.
  - Estimate: 3–5 hours
  - Notes: Use `BoilerGateway.get_ch_temperature()`, `get_ch_setpoint()` and `set_ch_setpoint()`.

- [ ] Add `button` entities for adapter commands (reboot, reset errors)
  - Files to add/modify:
    - [custom_components/ectocontrol_modbus_controller/entities/button.py](custom_components/ectocontrol_modbus_controller/entities/button.py#L1)
    - Register platform in `manifest.json` and forward entry setups in `__init__.py`.
  - Tests:
    - `tests/test_entities_buttons.py` to assert calls to `BoilerGateway.reboot_adapter()` and `reset_boiler_errors()` and subsequent coordinator refresh.
  - Estimate: 1–2 hours
  - Notes: Replace or keep services as compatibility shim if desired.

- [ ] Implement full set of switch/number entities per plan
  - Files to add/modify:
    - `custom_components/ectocontrol_modbus_controller/entities/switch.py` (expand for DHW enable, Reboot button fallback if needed)
    - `custom_components/ectocontrol_modbus_controller/entities/number.py` (add CH min/max, DHW setpoint, max modulation)
  - Tests:
    - Extend `tests/test_entities.py`/`test_entities_more.py` to cover each entity's read/write and invalid value handling.
  - Estimate: 3–6 hours

- [ ] Add adapter-type and adapter-reboot-code sensors
  - Files to modify:
    - `custom_components/ectocontrol_modbus_controller/boiler_gateway.py` — add `get_adapter_type()` and `get_adapter_reboot_code()` helpers reading MSB/LSB of `REGISTER_STATUS`.
    - `custom_components/ectocontrol_modbus_controller/entities/sensor.py` — add sensor descriptions and exposure.
  - Tests:
    - `tests/test_boiler_gateway.py` coverage for new getters and invalid markers.
  - Estimate: 1 hour

- [ ] Add centralized `RetryPolicy` and integrate with coordinator/protocol
  - Files to add/modify:
    - `custom_components/ectocontrol_modbus_controller/retry.py` — implement `execute_with_retry()` (exponential backoff) per plan.
    - Integrate calls in `coordinator.py` and write helpers for control writes (1 retry for commands, up to 3 for reads).
  - Tests:
    - `tests/test_modbus_protocol_edgecases.py` or new `tests/test_retry.py` to simulate timeouts and verify backoff/retries.
  - Estimate: 2–4 hours

- [ ] Narrow `config_flow` slave ID range to plan (1–32) or document reason to allow up to 247
  - Files to modify:
    - `custom_components/ectocontrol_modbus_controller/config_flow.py`
  - Tests:
    - `tests/test_config_flow.py` adjust expected validation behavior.
  - Estimate: 15–30 minutes
  - Notes: Current code allows 1–247; change only if plan strictness required.

- [ ] Replace standalone service handlers with HA `button` platform (optional, see previous task)
  - Files to modify:
    - `custom_components/ectocontrol_modbus_controller/__init__.py` — remove or keep service registration as compatibility shim.
  - Tests:
    - `tests/test_services_cleanup.py` update to check services removal if removed.
  - Estimate: 30–60 minutes

- [ ] Update tests to assert availability logic and invalid markers per plan
  - Files to modify:
    - `tests/test_entities.py` and others to verify entities return `None` and `available` is False when data invalid per markers (0x7FFF, 0xFF, 0x7F).
  - Estimate: 1–2 hours

- [ ] Document and add examples for discovery and multi-register write optimization (future/optional)
  - Files to add:
    - `docs/DISCOVERY.md` and `docs/MULTI_WRITE.md`
  - Estimate: 2–4 hours (optional)

---

## PR Checklist Template for reviewers
Use the template below in PR description to help reviewers verify each item.

- [ ] All new platforms added to `manifest.json` and forwarded in `async_setup_entry`.
- [ ] New entities have unique IDs in the format `ectocontrol_{slave_id}_{feature}`.
- [ ] Tests added/updated and all tests pass locally (`pytest -q`).
- [ ] New helper methods added to `BoilerGateway` when interacting with registers.
- [ ] Retry/backoff implemented for Modbus read/write operations where appropriate.
- [ ] Documentation updated for any new user-facing options or limitations.

---

If you want, I can implement one of these items now (for example, add the `button` platform and tests, or implement the `climate` entity). Otherwise you can commit this checklist and open a PR referencing it.
