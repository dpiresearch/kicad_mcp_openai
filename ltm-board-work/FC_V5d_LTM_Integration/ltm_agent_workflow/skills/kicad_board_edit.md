# Skill: KiCad Board Edit

Apply repeatable KiCad edits to the copied FC_V5d project only.

Checklist:

- Never edit the source project under `/Users/dpang/dev/PROVES`.
- Keep requirement callouts on `Cmts.User` or `Dwgs.User` until the schematic/netlist pass is complete.
- Do not route RF, power, CAN, or umbilical nets until the LTM connector pinout is confirmed from machine-readable LTM design files.
- Preserve legacy radio footprints until the replacement/removal decision is reviewed.
- Export a plot after every edit and confirm the board file still loads with KiCad.
