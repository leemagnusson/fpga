"""Single source of truth for the t1s_tap circuit: parts, pins -> nets.
Used by gen_sch.py (schematic) and gen_pcb.py (board) so they cannot disagree."""

# ref: (lib symbol, value, footprint, {pin: net}, description)
PARTS = {
    "U1": ("t1s_tap:SN65HVD78", "SN65HVD78", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
           {"1": "RX", "2": "GND", "3": "DE", "4": "TXD", "5": "GND", "6": "A", "7": "B", "8": "+3V3"},
           "3.3 V 50 Mbps half-duplex RS-485 transceiver (alt. ADM3065E)"),
    "C1": ("Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric",
           {"1": "+3V3", "2": "GND"}, "decoupling"),
    "R1": ("Device:R", "100", "Resistor_SMD:R_0603_1608Metric",
           {"1": "A", "2": "TERM"}, "optional bus termination (with JP1)"),
    "JP1": ("Jumper:SolderJumper_2_Open", "TERM", "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
            {"1": "TERM", "2": "B"}, "close to terminate the bus here"),
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
           # footprint pin -> net. Pmod pins 1..6 = odd row (1,3,5,7,9,11), Pmod 7..12 = even row (2,4,...,12)
           {"1": "RX", "3": "TRIG0", "5": "TRIG1", "7": "TRIG2", "9": "GND", "11": "+3V3",
            "2": "TRIG3", "4": "DE", "6": "TXD", "8": "SPARE", "10": "GND", "12": "+3V3"},
           "Pmod host connector (right angle male)"),
    "J2": ("Connector:Screw_Terminal_01x02", "T1S bus", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-2-3.5-H_1x02_P3.50mm_Horizontal",
           {"1": "A", "2": "B"}, "10BASE-T1S pair"),
    "J3": ("Connector_Generic:Conn_01x03", "T1S bus", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
           {"1": "A", "2": "B", "3": "GND"}, "10BASE-T1S pair, header"),
    "J4": ("Connector:Conn_Coaxial", "TRIG0", "Connector_Coaxial:SMA_Amphenol_132289_EdgeMount",
           {"1": "SMA", "2": "GND"}, "trigger 0 to scope"),
    "J5": ("Connector_Generic:Conn_01x05", "TRIG", "Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
           {"1": "T0", "2": "T1", "3": "T2", "4": "T3", "5": "GND"}, "trigger outputs"),
    "TP1": ("Connector:TestPoint", "SPARE", "TestPoint:TestPoint_Pad_D1.5mm", {"1": "SPARE"}, "Pmod IO10"),
}

# ref -> (manufacturer, manufacturer part number). Parts without an entry (solder
# jumper, test point) are bare copper and excluded from the BOM and placement file.
MPN = {
    "U1": ("Texas Instruments", "SN65HVD78D"),
    "C1": ("Yageo", "CC0603KRX7R9BB104"),           # 100 nF X7R 50 V 0603
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
