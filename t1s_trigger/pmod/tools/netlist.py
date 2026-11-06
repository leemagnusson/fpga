"""Single source of truth for the t1s_tap circuit: parts, pins -> nets.
Used by gen_sch.py (schematic) and gen_pcb.py (board) so they cannot disagree."""

# ref: (lib symbol, value, footprint, {pin: net}, description)
PARTS = {
    "U1": ("t1s_tap:SN65HVD78", "SN65HVD78", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
           {"1": "RX", "2": "GND", "3": "DE", "4": "TXD", "5": "GND", "6": "A", "7": "B", "8": "+3V3"},
           "3.3 V 50 Mbps half-duplex RS-485 transceiver (alt. ADM3065E)"),
    # second receiver with A/B swapped: its output goes low when the line is positive, U1's when it is
    # negative, so the FPGA sees positive / negative / idle instead of a two-level signal that reads idle
    # and positive alike. Driver pins tied off.
    "U2": ("t1s_tap:SN65HVD78", "SN65HVD78", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
           {"1": "RXN", "2": "GND", "3": "GND", "4": "GND", "5": "GND", "6": "B", "7": "A", "8": "+3V3"},
           "second receiver, inputs swapped (alt. ADM3065E)"),
    "C1": ("Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric",
           {"1": "+3V3", "2": "GND"}, "decoupling U1"),
    "C2": ("Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric",
           {"1": "+3V3", "2": "GND"}, "decoupling U2"),
    "R1": ("Device:R", "100", "Resistor_SMD:R_0603_1608Metric",
           {"1": "A", "2": "TERM"}, "optional bus termination (with JP1)"),
    "JP1": ("Connector_Generic:Conn_01x02", "TERM", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
            {"1": "TERM", "2": "B"}, "termination jumper: shunt fitted = 100 R (R1) across A/B"),
    "R2": ("Device:R", "49.9", "Resistor_SMD:R_0603_1608Metric",
           {"1": "SMA", "2": "TRIG0"}, "SMA source termination"),
    "R3": ("Device:R", "1k", "Resistor_SMD:R_0603_1608Metric",
           {"1": "+3V3", "2": "LEDA"}, "activity LED"),
    "R4": ("Device:R", "10k", "Resistor_SMD:R_0603_1608Metric",
           {"1": "DE", "2": "GND"}, "driver off by default"),
    "R5": ("Device:R", "33", "Resistor_SMD:R_0603_1608Metric", {"1": "T0", "2": "TRIG0"}, ""),
    "R6": ("Device:R", "33", "Resistor_SMD:R_0603_1608Metric", {"1": "T1", "2": "TRIG1"}, ""),
    "R7": ("Device:R", "33", "Resistor_SMD:R_0603_1608Metric", {"1": "T2", "2": "TRIG2"}, ""),
    "R8": ("Device:R", "33", "Resistor_SMD:R_0603_1608Metric", {"1": "T3", "2": "TRIG3"}, ""),
    "D1": ("Device:LED", "GREEN", "LED_SMD:LED_0603_1608Metric",
           {"1": "RX", "2": "LEDA"}, "lit while the line is active"),
    "J1": ("Connector_Generic:Conn_02x06_Odd_Even", "Pmod", "Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Horizontal",
           # footprint pad -> net. The KiCad footprint numbers the odd (upper) row 1,3,..,11 and the even
           # (lower) row 2,4,..,12 starting at the pad that ends up on the RIGHT when the header points away
           # from you (components up). The Pmod standard puts pin 1 on the LEFT in that view, so
           # Pmod pin n = pad 13-2n for n = 1..6 and pad 26-2n for n = 7..12.
           {"11": "RX", "9": "TRIG0", "7": "TRIG1", "5": "TRIG2", "3": "GND", "1": "+3V3",
            "12": "TRIG3", "10": "DE", "8": "TXD", "6": "RXN", "4": "GND", "2": "+3V3"},
           "Pmod host connector (right angle male)"),
    "J2": ("Connector:Screw_Terminal_01x02", "T1S bus", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-2-3.5-H_1x02_P3.50mm_Horizontal",
           {"1": "A", "2": "B"}, "10BASE-T1S pair"),
    "J3": ("Connector_Generic:Conn_01x03", "T1S bus", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
           {"1": "A", "2": "B", "3": "GND"}, "10BASE-T1S pair, header"),
    "J4": ("Connector:Conn_Coaxial", "TRIG0", "Connector_Coaxial:SMA_Amphenol_132289_EdgeMount",
           {"1": "SMA", "2": "GND"}, "trigger 0 to scope"),
    "J5": ("Connector_Generic:Conn_01x05", "TRIG", "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
           {"1": "T0", "2": "T1", "3": "T2", "4": "T3", "5": "GND"}, "trigger outputs"),
}

# ref -> (manufacturer, manufacturer part number). Parts without an entry would be
# excluded from the BOM and placement file (none at the moment).
MPN = {
    "U1": ("Texas Instruments", "SN65HVD78D"),
    "U2": ("Texas Instruments", "SN65HVD78D"),
    "C1": ("Yageo", "CC0603KRX7R9BB104"),           # 100 nF X7R 50 V 0603
    "C2": ("Yageo", "CC0603KRX7R9BB104"),
    "R1": ("Yageo", "RC0603FR-07100RL"),
    "R2": ("Yageo", "RC0603FR-0749R9L"),
    "R3": ("Yageo", "RC0603FR-071KL"),
    "R4": ("Yageo", "RC0603FR-0710KL"),
    "R5": ("Yageo", "RC0603FR-0733RL"),
    "R6": ("Yageo", "RC0603FR-0733RL"),
    "R7": ("Yageo", "RC0603FR-0733RL"),
    "R8": ("Yageo", "RC0603FR-0733RL"),
    "D1": ("Kingbright", "APT1608SGC"),              # green 0603, cathode = pin 1
    "J1": ("Sullins", "PRPC006DBAN-M71"),            # 2x6 2.54 mm right-angle male
    "JP1": ("Sullins", "PRPC002SAAN-RC"),            # 1x2 header; needs a 2.54 mm shunt (e.g. Sullins SPC02SYAN)
    "J2": ("Phoenix Contact", "1984617"),            # PT 1,5/2-3.5-H
    "J3": ("Sullins", "PRPC003SAAN-RC"),
    "J4": ("Amphenol RF", "132289"),                 # SMA end launch, 1.6 mm board
    "J5": ("Sullins", "PRPC005SAAN-RC"),
}

POWER_NETS = ("+3V3", "GND")

def nets():
    n = {}
    for ref, (_, _, _, pins, _) in PARTS.items():
        for pin, net in pins.items():
            n.setdefault(net, []).append((ref, pin))
    return n
