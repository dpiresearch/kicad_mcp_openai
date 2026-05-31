# Skill: Verification

Verify each integration pass against `requirements_memory.json`.

Checklist:

- Load the board with KiCad Python.
- Export a visual plot of the modified PCB.
- Run ERC/DRC once schematic netlist changes begin.
- Confirm LTM power, CAN, umbilical, serial loader, telemetry, I2C, and RF obligations are represented in schematic and board artifacts.
- Report any captured requirement that remains only documented and not yet electrically implemented.
