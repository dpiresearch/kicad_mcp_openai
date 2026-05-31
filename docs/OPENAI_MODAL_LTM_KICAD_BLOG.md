# From Claude-Centric KiCad Automation to OpenAI, Modal, and Autonomous PCB Review

On May 30, 2026, we used the KiCAD MCP Server as a working lab for a larger question: can an AI coding agent move beyond writing code and start participating in real PCB design work?

The project started with a software change. The existing KiCAD MCP Server was oriented around Claude-era assistant workflows. We modified it so OpenAI Codex could drive KiCad through MCP, added parallel OpenAI/Modal planning agents, then used those new capabilities on an actual satellite electronics task: copying and adapting an EPS board, integrating PC/104 mechanical geometry, cleaning up a USB-C design, and iterating a PCB layout with visual snapshots and DRC feedback.

The result was not a finished flight board, but it was a meaningful step toward autonomous electrical CAD work: the assistant could inspect schematics and PCB layouts, render its own visual feedback, make placement and routing changes, run DRC, reject bad routing attempts, and keep a running engineering log.

## Projects Involved

The work touched four main project areas:

- `KiCAD-MCP-Server`
  - Main automation server.
  - Modified to expose OpenAI-friendly MCP tools, Modal/OpenAI parallel agents, and design snapshot tooling.

- `joan_sat/eps_board`
  - Working KiCad project copied into `/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board`.
  - This became the active board for schematic-to-PCB sync, placement, routing, copper pours, and DRC checks.

- `1KCubeSat`
  - Source hardware repository used for EPS and PC/104 assets.
  - PC/104 board source: `/Users/dpang/dev/1KCubeSat/1KCubeSat_Joan/eps_board/PC104/PC104_burns/PC104.kicad_pcb`
  - Custom footprint library source: `/Users/dpang/dev/1KCubeSat/1KCubeSat_Hardware/kicad_libraries/footprint_custom.pretty`

- `ltm-board-work`
  - Earlier work area for the LTM integration and USB-C footprint reference.
  - Used while replacing the USB-C component and validating the footprint `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12`.

## Step 1: Moving the MCP Server Toward OpenAI

The first change was conceptual and architectural: make the KiCad automation stack work naturally with OpenAI Codex rather than a Claude-specific workflow.

The server README now describes the system as an MCP bridge for "AI assistants like OpenAI Codex." More importantly, the code now includes OpenAI/Modal agent orchestration tools:

- `src/tools/agents.ts`
- `python/agent_orchestrator.py`
- `python/agents/parallel_agents.py`

These tools expose:

- `get_parallel_agent_status`
- `run_parallel_agents`

The design separates planning from mutation. Parallel agents can review a KiCad task as schematic architect, layout engineer, and DFM reviewer, but actual KiCad file edits remain serialized in the local MCP worker. That matters because PCB mutation is stateful: two independent processes moving footprints or changing nets at the same time would be an excellent way to create a very confident mess.

Modal support was added as an optional remote execution backend. If Modal and the OpenAI Agents SDK are installed, analysis can fan out remotely; otherwise it falls back to local threaded heuristic agents. The default OpenAI model is controlled by `KICAD_MCP_AGENT_MODEL`, with `gpt-4.1-mini` as the default in the orchestrator.

## Step 2: Adding Visual Feedback Tools

The largest practical improvement was visual feedback. Before this, the user had to open KiCad, take screenshots, attach them, and ask the assistant to react. We added tooling so the assistant could capture schematic and PCB views itself.

The new viewer tooling lives in:

- `src/tools/viewer.ts`
- `python/commands/board/view.py`

The key MCP-facing tool is `capture_design_snapshot`. It resolves the active schematic and PCB, renders timestamped visual snapshots, stores them under `snapshots/visual-feedback`, and can return images inline.

Under the hood, PCB rendering uses `kicad-cli pcb export svg`, with PNG conversion fallback support through PyMuPDF, Inkscape, or ImageMagick. In practice, this let the agent use snapshots as a control loop:

1. Modify schematic or board.
2. Export SVG/PNG.
3. Inspect the image.
4. Run DRC.
5. Keep, revise, or reject the change.

That changed the workflow from "the human reports what looks wrong" to "the assistant checks its own work."

## Step 3: Cleaning Up the Schematic

The first visual problems appeared in the schematic. The LTM integration sheet had overlapping content, and the drilled-down sheet looked incomplete. We repositioned and rebuilt the LTM schematic content so it was readable, then moved on to the EPS board copy and USB-C replacement.

Later, the copied EPS schematic had loose wiring around the new USB-C component. The USB-C pins, CC pull-downs, shield, VBUS, and GND connections needed cleanup. The visual snapshot workflow helped catch disconnected-looking and overlapping regions around the connector.

![USB-C schematic cleanup](/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_usb_c_cleanup_schematic.png)

The schematic stage produced one of the more important project lessons: visual correctness and electrical correctness are related, but not identical. A schematic can look cleaner while still missing net assignments, and a PCB can have beautiful placement while still failing DRC. The workflow needed both visual snapshots and machine checks.

## Step 4: Copying the EPS Board and Importing PC/104 Geometry

The active board was copied into:

`/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board`

We then imported the PC/104 board geometry from the 1KCubeSat project. The imported features included:

- board outline on `Edge.Cuts`
- four mounting holes
- two 52-pin PC/104 headers

The imported duplicate `J1` references were renamed to:

- `J_PC104_A`
- `J_PC104_B`

Mounting holes were renamed:

- `MH_PC104_1`
- `MH_PC104_2`
- `MH_PC104_3`
- `MH_PC104_4`

Baseline target PCB:

![Empty target PCB](/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_01_empty_target_pcb.svg.png)

After PC/104 import:

![PC/104 import](/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_02_pc104_import.svg.png)

This turned an empty PCB file into a mechanically meaningful board: the assistant now had a real outline, mounting constraints, and connector keepout pressure to work around.

## Step 5: Schematic-to-PCB Sync and Library Recovery

The first schematic-to-PCB sync added 45 footprints and 57 nets. It also exposed a dependency problem: some schematic footprints referenced libraries or footprint names missing from the local KiCad install.

The key missing library was `footprint_custom`. We found it in the 1KCubeSat hardware repo and added a project-local `fp-lib-table`:

`/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/fp-lib-table`

That table maps:

`footprint_custom -> /Users/dpang/dev/1KCubeSat/1KCubeSat_Hardware/kicad_libraries/footprint_custom.pretty`

After rerunning sync:

- 15 additional footprints were added.
- 41 additional nets were added.
- 141 pads were assigned.
- `U16` appeared on the PCB with the custom MSOP footprint.
- Battery holders, diodes, charger/power ICs, and other custom components became available.

The PCB now had 68 footprints and no off-board footprints, but placement was rough and crowded.

![Custom footprints placed roughly](/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_11_custom_footprints_placed.svg.png)

At this stage, DRC reported 195 violations and 70 unconnected items. That was not failure; it was the board telling us what the next phase had to be.

## Step 6: Proper Placement

The placement pass moved the design from "all footprints exist" to "the board has a plausible physical organization."

Major placement decisions:

- `BT1` and `BT3` were rotated horizontally and placed inside the PC/104 outline.
- The PC/104 headers and mounting holes were kept clear.
- USB-C stayed accessible on the left board edge.
- Charger, regulator, and power ICs were grouped into a central electronics channel.
- `U16` was placed with the other charger/power ICs.
- `J4` through `J9` were grouped on the right side and pulled inward from the board edge.
- Thermistor and auxiliary connectors were moved away from battery and mounting-hole keepouts.

After the proper placement pass:

![Proper placement pass](/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_15_proper_placement_pass.svg.png)

DRC improved from 195 violations to 39 violations. Unconnected items increased to 84 because stale provisional traces were deliberately cleared before placement evaluation. That was the right trade: routing on top of bad placement is usually false progress.

## Step 7: Conservative Local Routing

Next came short, low-risk routing. The assistant routed only local connections that could be completed without creating new DRC errors:

- duplicate or adjacent pins on `U4`, `U15`, `U16`, and `U2`
- bottom test-point pairs `TP3/TP11`, `TP4/TP12`, `TP5/TP13`, and `TP6/TP14`
- local GND links between `J2/TH1`, `R22/R23`, and paired USB-C shield pads

Accepted result:

- 17 local traces
- DRC stayed flat at 39 violations
- unconnected items dropped from 84 to 67

![Conservative trace pass](/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_19_final_conservative_trace_pass.svg.png)

The assistant also tried broader charger-IC fanouts, but rejected them because DRC reported real short and clearance errors around fine-pitch charger pads. This was one of the most important behavioral improvements: the system was not just making edits; it was testing and backing out unsafe ones.

## Step 8: GND Copper Pour

A lot of remaining ratsnest was ground. We added filled `GND` copper pours on both `F.Cu` and `B.Cu`, using the PC/104 board outline. KiCad first flagged thermal-relief starvation on tight USB-C and charger pads, so the pours were switched to solid pad connections.

Accepted result:

- DRC stayed flat at 39 violations.
- unconnected items dropped from 67 to 41.
- 26 additional connections were cleared by the pour.

![GND pour final](/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_23_ground_pour_final.svg.png)

This was the best single electrical improvement in the routing phase.

## Step 9: Vias and a 4-Layer Experiment

The final routing experiment tested whether vias could finish more of the remaining ratsnest.

On the original 2-layer stack, via-assisted routing reduced ratsnest count but failed DRC because back-side tracks crossed exposed or GND pad structures.

So the board was converted to a 4-copper-layer stack. With an internal signal layer available, one via-assisted route was accepted:

- `VOUT` from `U16` pad 14 to `U2` pad 14
- top-layer pad escapes
- through vias
- `In1.Cu` internal detour around the through-hole/GND pad field

Accepted result:

- DRC stayed flat at 39 violations.
- unconnected items dropped from 41 to 40.
- board now has 4 copper layers and 24 track/via items.

An attempted `PGOOD` internal route was rejected because front-side escapes near adjacent fine-pitch pads caused new clearance errors.

Final 4-layer SVG snapshot:

`/Users/dpang/dev/KiCAD-MCP-Server/joan_sat/eps_board/snapshots/visual-feedback/2026-05-30_29_4layer_vout_final.svg`

## Significant Improvements

The project produced improvements in both software capability and PCB state.

Software improvements:

- OpenAI-oriented README and workflow framing.
- OpenAI Agents SDK support through `python/agents/parallel_agents.py`.
- Optional Modal backend for remote parallel agent execution.
- MCP tools for agent status and parallel agent planning.
- Schematic/PCB snapshot tooling for autonomous visual review.
- PCB rendering through `kicad-cli` instead of depending only on interactive KiCad UI screenshots.
- A running project log that records snapshots, DRC reports, accepted changes, and rejected experiments.

PCB design improvements:

- EPS board copied into a clean working area.
- PC/104 mechanical outline, mounting holes, and headers imported.
- USB-C schematic wiring cleaned up.
- Missing custom footprint library connected through a local `fp-lib-table`.
- `U16` and other custom footprints synced into the board.
- Proper placement pass completed.
- DRC reduced from 195 violations after rough sync to 39 current violations.
- Unconnected items reduced from 84 after placement to 40 after routing, pours, and one accepted 4-layer via route.
- GND copper pours added and validated.
- Board converted to a 4-layer stack for harder routing experiments.

## Tools Used

Core tools:

- OpenAI Codex in the Codex desktop app
- KiCAD MCP Server
- KiCad 9.0.7
- `kicad-cli`
- KiCad Python/`pcbnew`
- Model Context Protocol tools
- OpenAI Agents SDK integration
- Modal integration

Engineering workflow tools:

- `rg`, `sed`, `find`, and Git for repo inspection
- KiCad DRC reports
- KiCad SVG export
- Quick Look thumbnail generation for PNG previews
- MCP visual snapshot tooling
- project-local `PCB_INTEGRATION_LOG.md`

## How Long It Took

The active visual-design log spans a single afternoon on May 30, 2026. The PCB snapshot/DRC sequence ran from the early board import work through the final 4-layer routing checkpoint at about 5:16 PM local time.

Based on the file timestamps and session log, the hands-on PCB iteration took roughly four to five hours. The broader project, including the OpenAI/Modal server changes, schematic cleanup, PCB copy, PC/104 integration, placement, routing, pours, and 4-layer experiment, fit into a same-day working session.

## What Still Remains

The board is not fabrication-ready. The remaining DRC count is still 39, and the ratsnest still has 40 unconnected items.

The remaining issues are mostly:

- imported PC/104 header courtyard/silkscreen/library warnings
- silkscreen overlap and clipped labels
- non-GND charger, power, and status nets that need careful multi-layer routing
- fine-pitch escape constraints around charger ICs

The next best engineering step is not to blindly autoroute. It is to revisit placement around the charger IC row, create cleaner escape corridors, then route the remaining non-GND nets with a deliberate layer strategy.

## Takeaway

This project showed that an AI assistant can become more than a code generator in an EDA workflow. With the right MCP tools, visual snapshots, DRC loops, and a willingness to reject bad edits, the assistant can participate in real PCB design iteration.

The most important shift was visual autonomy. Once the assistant could take its own schematic and PCB snapshots, the conversation changed. The user no longer had to be the camera operator. The assistant could see, correct, verify, and document its own work.

That is the beginning of a much more useful kind of hardware automation.
