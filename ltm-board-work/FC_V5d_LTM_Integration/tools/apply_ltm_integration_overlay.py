#!/usr/bin/env python3
"""Apply a repeatable AmSat LTM integration overlay to the copied KiCad board."""

from __future__ import annotations

from pathlib import Path

import pcbnew


MM = 1_000_000
BOARD_FILE = Path(__file__).resolve().parents[1] / "FC_V5d_Production_Rev2.kicad_pcb"
MARKER = "LTM END-STACK INTERFACE"
OVERLAY_TEXT_MARKERS = (
    MARKER,
    "POWER: switched VSYS",
    "CAN: primary host link",
    "UMBILICAL: Attached high",
    "TLM/GPIO/I2C:",
    "RF: host must provide 50R",
    "LEGACY RADIO REVIEW:",
)
OVERLAY_RECTS = (
    (144.5, 49.0, 230.0, 140.0, pcbnew.Dwgs_User),
    (147.0, 51.5, 228.0, 78.0, pcbnew.Cmts_User),
)


def mm(value: float) -> int:
    return int(round(value * MM))


def add_text(board: pcbnew.BOARD, text: str, x: float, y: float, size: float = 1.15) -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetLayer(pcbnew.Cmts_User)
    item.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    item.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    item.SetTextThickness(mm(0.14))
    item.SetMultilineAllowed(True)
    board.Add(item)


def add_rect(board: pcbnew.BOARD, x1: float, y1: float, x2: float, y2: float, layer: int) -> None:
    item = pcbnew.PCB_SHAPE(board)
    item.SetShape(pcbnew.SHAPE_T_RECT)
    item.SetLayer(layer)
    item.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
    item.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
    item.SetWidth(mm(0.18))
    board.Add(item)


def remove_existing_overlay(board: pcbnew.BOARD) -> None:
    for drawing in list(board.GetDrawings()):
        if isinstance(drawing, pcbnew.PCB_TEXT) and any(
            marker in drawing.GetText() for marker in OVERLAY_TEXT_MARKERS
        ):
            board.Remove(drawing)
        elif isinstance(drawing, pcbnew.PCB_SHAPE) and drawing.GetShape() == pcbnew.SHAPE_T_RECT:
            start = drawing.GetStart()
            end = drawing.GetEnd()
            for x1, y1, x2, y2, layer in OVERLAY_RECTS:
                if (
                    drawing.GetLayer() == layer
                    and start.x == mm(x1)
                    and start.y == mm(y1)
                    and end.x == mm(x2)
                    and end.y == mm(y2)
                ):
                    board.Remove(drawing)
                    break
                board.Remove(drawing)


def apply_overlay(board: pcbnew.BOARD) -> None:
    # Board bounding box is about x=143.3..231.4 mm, y=47.5..142.1 mm.
    for rect in OVERLAY_RECTS:
        add_rect(board, *rect)

    add_text(
        board,
        "LTM END-STACK INTERFACE\n"
        "3-board AmSat LTM; no PC-104 pass-through.\n"
        "Confirm final connector geometry from LTM LIHU Gerbers/KiCad.",
        148.0,
        53.0,
        1.35,
    )
    add_text(
        board,
        "POWER: switched VSYS 5.0V +/-5%, size for ~2.9W max.\n"
        "Keep LTM unpowered until transmit-safe and antennas deployed.",
        148.0,
        80.5,
    )
    add_text(
        board,
        "CAN: primary host link, 29-bit IDs. Host source >=8 when commanding LTM dest 0/3.",
        148.0,
        90.0,
    )
    add_text(
        board,
        "UMBILICAL: Attached high on bench/USB, low in flight; inhibits transmit and gates loader behavior.",
        148.0,
        96.5,
    )
    add_text(
        board,
        "TLM/GPIO/I2C: TLM1-4 are 0-3.3V or GND if unused. LTM is I2C master; expose reset as needed.",
        148.0,
        103.0,
    )
    add_text(
        board,
        "RF: host must provide 50R VHF and UHF antenna paths to LTM coax/SMA interfaces.",
        148.0,
        109.5,
    )
    add_text(
        board,
        "LEGACY RADIO REVIEW: U4 RFM98PW + RF1 MMCX area should be replaced or isolated for LTM host use.",
        148.0,
        116.0,
    )


def main() -> None:
    board = pcbnew.LoadBoard(str(BOARD_FILE))
    remove_existing_overlay(board)
    apply_overlay(board)
    pcbnew.SaveBoard(str(BOARD_FILE), board)
    print(f"Applied LTM integration overlay to {BOARD_FILE}")


if __name__ == "__main__":
    main()
