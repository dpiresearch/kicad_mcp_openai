# One-Minute Video Script

**Title:** OpenAI Codex Meets KiCad: Autonomous PCB Design with MCP

**0:00-0:07**  
We started with the KiCAD MCP Server and modified it for an OpenAI Codex workflow, replacing the old Claude-oriented assumptions with OpenAI-friendly tools and agent orchestration.

**0:07-0:15**  
Then we added Modal and OpenAI parallel agents: schematic, layout, and DFM reviewers that can fan out planning work while keeping actual KiCad edits serialized and safe.

**0:15-0:23**  
The biggest unlock was visual feedback. We added schematic and PCB snapshot tools so the assistant could inspect its own work instead of waiting for manually attached screenshots.

**0:23-0:34**  
Using that workflow, we copied the EPS board into a new project, imported the PC/104 board outline, mounting holes, and headers, replaced and rewired the USB-C connector, and restored the missing custom footprint library.

**0:34-0:45**  
Next came placement. The board went from a crowded rough sync to a clean PC/104 layout with batteries horizontal, USB-C accessible, headers pulled in from the edge, and `U16` placed in the central power channel.

**0:45-0:54**  
For routing, we accepted only DRC-clean changes: local traces, solid GND pours, and one 4-layer via-assisted `VOUT` route. Bad trace attempts were tested, detected, and rejected.

**0:54-1:00**  
In one afternoon, the workflow reduced rough-placement DRC from 195 violations to 39 and cut unconnected items from 84 to 40. More importantly, it proved Codex can see, edit, verify, and document PCB design work.

## Suggested Visuals

- Empty board: `/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_01_empty_target_pcb.svg.png`
- PC/104 import: `/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_02_pc104_import.svg.png`
- USB-C schematic cleanup: `/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_usb_c_cleanup_schematic.png`
- Rough custom placement: `/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_11_custom_footprints_placed.svg.png`
- Proper placement: `/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_15_proper_placement_pass.svg.png`
- GND pour: `/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_23_ground_pour_final.svg.png`
- Final 4-layer SVG: `/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_29_4layer_vout_final.svg`
