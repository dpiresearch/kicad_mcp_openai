# AmSat LTM Integration Notes

Source board copied from:
`/Users/dpang/dev/PROVES/flight_controller_board/FC_V5d_Production_Rev2`

ICD source reviewed:
`/Users/dpang/Documents/smallsat/RF/LTM-1 Generic ICD_v2.5.pdf`

This is an integration scaffold for adapting the FC_V5d flight-controller design to host the AmSat Linear Transponder Module (LTM). It intentionally keeps the original copied KiCad project intact and adds LTM-specific requirements, board-layer callouts, and an agent-verifiable workflow around the copied design.

## LTM Host Assumptions

- LTM is a hosted radio/transponder module, not a replacement flight computer.
- LTM is a three-board stack and does not pass PC-104 bus lines through; place it at one end of the stack.
- Host supplies LTM power as 5.0 V +/- 5%, with about 2.9 W maximum expected draw.
- Host should keep LTM unpowered until transmit-safe conditions are met and antennas are deployed.
- Host provides nominal 50 ohm VHF and UHF antenna interfaces for the LTM coax/SMA antenna connections.
- LTM communicates primarily over CAN using 29-bit identifiers. The host should reserve source IDs 8 and above when commanding LTM destinations 0 or 3.
- LTM optional I2C interface is master-only from the LTM side. Treat host telemetry devices as LTM-readable peripherals, not host-driven LTM peripherals.
- Umbilical Attached must be high on the bench/USB umbilical path and low in flight. It inhibits transmit and controls bootloader behavior during power/reset.
- The LIHU serial console/code-loader path must remain accessible after spacecraft integration through the umbilical path.
- Unused LTM analog telemetry inputs should be tied to ground.

## FC_V5d Touch Points

- Legacy modular radio schematic area was removed because the LTM is now the radio interface.
- The PCB still contains legacy radio footprints until the next layout pass removes or repurposes them.
- Existing I2C nets include `SCL0`/`SDA0`, `SCL1`/`SDA1`, and face/battery bus variants. The LTM I2C relationship is different because LTM is the master.
- Existing reset/debug/umbilical/inhibit circuitry should be reviewed for the LTM serial loader and Umbilical Attached behavior.

## OpenAI Agents / Modal-Inspired Workflow

The `modal-labs/openai-agents-python-example` pattern is represented here as explicit agent artifacts:

- `ltm_agent_workflow/requirements_memory.json`: persistent requirements memory extracted from the ICD and board scan.
- `ltm_agent_workflow/skills/*.md`: compact role prompts for specialized agents.
- `tools/apply_ltm_integration_overlay.py`: deterministic tool that applies the board overlay.

Recommended agent handoff:

1. `ltm_icd_review`: update requirements memory from the latest ICD revision.
2. `kicad_board_edit`: apply repeatable KiCad edits only after requirements are memory-backed.
3. `verification`: export plots, run DRC/ERC, and compare the design against the memory file.

## Current Board Modification

The copied PCB includes a non-fabrication `Cmts.User`/`Dwgs.User` overlay:

- LTM end-of-stack keepout/placement reminder.
- Power, CAN, umbilical, telemetry, GPIO, I2C, and RF antenna callouts.
- Legacy radio replacement marker.

This does not yet replace the full schematic netlist with a validated LTM connector harness. Use it as the starting point for the next electrical pass once the exact LTM LIHU connector/PC-104 pinout and Gerbers/KiCad files are available.

## Current Schematic Modification

The root schematic now contains a top-level hierarchical sheet named `AmSat LTM Interface`, backed by `LTM_Interface.kicad_sch`.

That sheet captures the current LTM host-interface placeholder nets:

- `LTM_VSYS_5V`, `GND`
- `LTM_POWER_ENABLE`
- `LTM_CAN_H`, `LTM_CAN_L`
- `LTM_UART_TX_TO_HOST`, `LTM_UART_RX_FROM_HOST`
- `LTM_UMBILICAL_ATTACHED`
- `LTM_I2C_SCL`, `LTM_I2C_SDA`, `LTM_I2C_RESET`
- `LTM_TLM1` through `LTM_TLM4`
- `LTM_GPIO1` through `LTM_GPIO4`
- `LTM_VHF_ANT_50R`, `LTM_UHF_ANT_50R`

The drill-down sheet now includes `J_LTM`, a 2x11 connector placeholder with grouped power, safety, CAN, UART, I2C, telemetry, GPIO, and RF handoff nets. The connector remains a placeholder; exact symbol, footprint, pin numbering, and pin assignments should be replaced after the LTM LIHU/PC-104 mechanical and pinout source files are available.
