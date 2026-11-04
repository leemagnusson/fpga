"""The circuit: an M.2 2280 key-M card with an Artix-7 XC7A50T (CSG325), PCIe
x4 Gen2 to the host, and four CAN FD transceivers.

Everything is expressed as parts with pins mapped to net names. Sheet names
group parts for the schematic; `place` gives the PCB placement (mm from the
board origin at the connector edge, centreline; +x right, +y away from the
connector).

Pin numbers/names come straight from the datasheets:
  TLV62569DBV  SOT-23-5   1 EN  2 GND  3 SW  4 VIN  5 FB            (buck 2 A, FB = 0.6 V)
  TPS62823DLC  VSON-8     1 EN  2 FB  3 AGND 4 NC  5 PGND 6 SW 7 VIN 8 PG   (buck 3 A, FB = 0.6 V, no pad)
  TLV755xPDBV  SOT-23-5   1 IN  2 GND  3 EN  4 NC  5 OUT             (fixed LDO)
  TPS22918DBV  SOT-23-6   1 VIN 2 GND  3 ON  4 CT  5 QOD  6 VOUT     (load switch)
  TPS61023DRL  SOT-563    1 FB  2 EN   3 VIN 4 GND 5 SW   6 VOUT     (boost, FB = 0.6 V)
  MCP2562FD    DFN-8      1 TXD 2 VSS  3 VDD 4 RXD 5 VIO  6 CANL 7 CANH 8 STBY, 9 = pad
  W25Q128JV    WSON-8     1 /CS 2 DO(IO1) 3 /WP(IO2) 4 GND 5 DI(IO0) 6 CLK 7 /HOLD(IO3) 8 VCC, 9 = pad
  ECS-2520MV   2520       1 Tri-state 2 GND 3 OUT 4 VDD
  PESD2CAN     SOT-23     1 line 2 line 3 GND
  M.2 socket 3 key M pin-out: PCIe M.2 spec rev 1.0 table 48 (platform side;
  PETx = host transmit = our receive, PERx = our transmit).
"""
import re
from model import Pin, Part, Design

FP = "artix_m2_canfd"
def fp(name): return f"{FP}:{name}"

# ---------------------------------------------------------------------------
# FPGA ball map from the AMD package file
def load_fpga_balls(path):
    balls = []
    for line in open(path):
        p = line.split()
        if len(p) >= 2 and re.match(r'^[A-Z]{1,2}[0-9]{1,2}$', p[0]):
            balls.append((p[0], p[1], p[3] if len(p) > 3 else ""))
    return balls

# ---------------------------------------------------------------------------
# small helpers
_counters = {}
def _next(prefix):
    _counters[prefix] = _counters.get(prefix, 0) + 1
    return f"{prefix}{_counters[prefix]}"

def two_pin(d, prefix, symbol, value, footprint, net1, net2, sheet, mpn="", desc="", place=None, zone=None, side="F"):
    ref = _next(prefix)
    pins = [Pin("1", "1", net1, side="L"), Pin("2", "2", net2, side="R")]
    part = Part(ref, value, symbol, footprint, pins, mpn=mpn, description=desc, sheet=sheet, place=place or (0, 0, 0, side))
    part.zone = zone or sheet
    return d.add(part)

# Manufacturer part numbers for the generic passives (assembly quotes need one per line):
# Yageo RC0402 1 % thick film, Murata GRM155 0402 capacitors.
DEFAULT_MPN = {
    ("R", "0402", "0R"): "RC0402JR-070RL", ("R", "0402", "1k"): "RC0402FR-071KL", ("R", "0402", "4k7"): "RC0402FR-074K7L",
    ("R", "0402", "10k"): "RC0402FR-0710KL", ("R", "0402", "68k"): "RC0402FR-0768KL", ("R", "0402", "100k"): "RC0402FR-07100KL",
    ("R", "0402", "200k"): "RC0402FR-07200KL", ("R", "0402", "732k"): "RC0402FR-07732KL",
    ("C", "0402", "100n"): "GRM155R71C104KA88D", ("C", "0402", "1u"): "GRM155R61A105KE15D", ("C", "0402", "1n"): "GRM1555C1H102JA01D",
}
def R(d, value, a, b, sheet, mpn="", place=None, size="0402", zone=None, side="F"):
    mpn = mpn or DEFAULT_MPN.get(("R", size, value), "")
    return two_pin(d, "R", "R", value, fp(f"R_{size}"), a, b, sheet, mpn, f"Resistor {value} {size}", place, zone, side)
def C(d, value, a, b, sheet, mpn="", place=None, size="0402", voltage="", zone=None, side="F"):
    mpn = mpn or DEFAULT_MPN.get(("C", size, value), "")
    return two_pin(d, "C", "C", value, fp(f"C_{size}"), a, b, sheet, mpn, f"Capacitor {value} {voltage} {size}".strip(), place, zone, side)
def L(d, value, a, b, sheet, mpn="", place=None, zone=None, side="F"):
    return two_pin(d, "L", "L", value, fp("L_0806"), a, b, sheet, mpn, f"Inductor {value} 2016", place, zone, side)
def FB(d, value, a, b, sheet, mpn="", place=None, zone=None, side="F"):
    return two_pin(d, "FB", "FB", value, fp("FB_0402"), a, b, sheet, mpn, "Ferrite bead 0402", place, zone, side)
def LED(d, color, cathode, anode, sheet, mpn="", place=None, zone=None, side="F"):
    return two_pin(d, "D", "LED", f"LED {color}", fp("LED_0402"), cathode, anode, sheet, mpn, f"LED {color} 0402", place, zone, side)

def ic(d, ref, value, symbol, footprint, pinmap, sheet, mpn="", desc="", place=None, zone=None, side="F"):
    """pinmap: list of (number, name, net, side)."""
    pins = [Pin(str(n), name, net, side=side) for n, name, net, side in pinmap]
    part = Part(ref, value, symbol, footprint, pins, mpn=mpn, description=desc, sheet=sheet, place=place or (0, 0, 0, side))
    part.zone = zone or sheet
    return d.add(part)

# ---------------------------------------------------------------------------
def build(pkg_path):
    d = Design("artix_m2_canfd")
    d.sheet_titles = {
        "m2": "M.2 connector and PCIe",
        "fpga_io": "FPGA I/O banks, config, JTAG, clock",
        "fpga_pwr": "FPGA power and decoupling",
        "power": "Power supplies and sequencing",
        "can": "CAN FD transceivers",
    }
    balls = load_fpga_balls(pkg_path)
    byname = {}
    for b, n, bank in balls:
        byname.setdefault(n, []).append(b)

    # ---- net names -------------------------------------------------------
    GND = "GND"
    V3IN = "VIN_3V3"      # straight from the M.2 connector
    V3 = "VCC3V3"         # switched, sequenced: FPGA VCCO, flash, CAN logic
    V1 = "VCC1V0"         # VCCINT + VCCBRAM
    V18 = "VCC1V8"        # VCCAUX
    AVCC = "MGTAVCC"      # 1.0 V transceiver
    AVTT = "MGTAVTT"      # 1.2 V transceiver
    V5CAN = "VCC5V_CAN"

    # ---- FPGA pin assignment (bank 34 for user I/O, 3.3 V) ----------------
    def io_pins(bank):
        return sorted([b for b, n, bk in balls if bk == bank and n.startswith("IO_")],
                      key=lambda b: (int(re.search(r'\d+', b).group()), b))
    # pick clock-capable pin for the oscillator, then generic I/O for the rest
    osc_ball = byname["IO_L12P_T1_MRCC_15"][0]           # E13
    perst_ball = byname["IO_L13P_T2_MRCC_15"][0]         # E15 (any I/O would do)
    bank34 = io_pins("34")
    user = iter(bank34)
    can_sig = {}
    for i in range(4):
        can_sig[i] = {"TXD": next(user), "RXD": next(user), "STBY": next(user)}
    led_balls = [next(user) for _ in range(4)]
    cfg = {n: byname[n][0] for n in ["IO_L1P_T0_D00_MOSI_14", "IO_L1N_T0_D01_DIN_14", "IO_L2P_T0_D02_14",
                                     "IO_L2N_T0_D03_14", "IO_L6P_T0_FCS_B_14", "IO_L3P_T0_DQS_PUDC_B_14"]}
    mgt = {n: byname[n][0] for n in byname if n.startswith("MGT")}

    fpga_net = {}  # ball -> net
    def setnet(ball, net):
        fpga_net[ball] = net
    for i in range(4):
        setnet(mgt[f"MGTPRXP{i}_216"], f"PCIE_RX{i}_P"); setnet(mgt[f"MGTPRXN{i}_216"], f"PCIE_RX{i}_N")
        setnet(mgt[f"MGTPTXP{i}_216"], f"PCIE_TX{i}_P"); setnet(mgt[f"MGTPTXN{i}_216"], f"PCIE_TX{i}_N")
    setnet(mgt["MGTREFCLK0P_216"], "PCIE_REFCLK_P"); setnet(mgt["MGTREFCLK0N_216"], "PCIE_REFCLK_N")
    setnet(mgt["MGTRREF_216"], "MGTRREF")
    setnet(osc_ball, "CLK100M")
    setnet(perst_ball, "PCIE_PERST_N")
    for i in range(4):
        for sig, ball in can_sig[i].items():
            setnet(ball, f"CAN{i}_{sig}")
    for i, b in enumerate(led_balls):
        setnet(b, f"LED{i}_N")
    setnet(cfg["IO_L1P_T0_D00_MOSI_14"], "QSPI_IO0")
    setnet(cfg["IO_L1N_T0_D01_DIN_14"], "QSPI_IO1")
    setnet(cfg["IO_L2P_T0_D02_14"], "QSPI_IO2")
    setnet(cfg["IO_L2N_T0_D03_14"], "QSPI_IO3")
    setnet(cfg["IO_L6P_T0_FCS_B_14"], "QSPI_CS_N")
    setnet(cfg["IO_L3P_T0_DQS_PUDC_B_14"], "PUDC_B")
    bank0 = {n: byname[n][0] for n in byname if n.endswith("_0") and not n.startswith("VCCO")}
    setnet(bank0["CCLK_0"], "QSPI_CLK")
    setnet(bank0["DONE_0"], "DONE"); setnet(bank0["INIT_B_0"], "INIT_B"); setnet(bank0["PROGRAM_B_0"], "PROGRAM_B")
    setnet(bank0["TCK_0"], "JTAG_TCK"); setnet(bank0["TMS_0"], "JTAG_TMS"); setnet(bank0["TDI_0"], "JTAG_TDI"); setnet(bank0["TDO_0"], "JTAG_TDO")
    setnet(bank0["M0_0"], "CFG_M0"); setnet(bank0["M1_0"], GND); setnet(bank0["M2_0"], GND)   # M[2:0]=001 master SPI
    setnet(bank0["CFGBVS_0"], V3)
    setnet(bank0["VREFP_0"], GND); setnet(bank0["VREFN_0"], GND); setnet(bank0["VP_0"], GND); setnet(bank0["VN_0"], GND)
    setnet(bank0["GNDADC_0"], GND); setnet(bank0["VCCADC_0"], "VCCADC"); setnet(bank0["VCCBATT_0"], V18)
    # power balls
    for b, n, bank in balls:
        if n == "GND": setnet(b, GND)
        elif n == "VCCINT" or n == "VCCBRAM": setnet(b, V1)
        elif n == "VCCAUX": setnet(b, V18)
        elif n.startswith("VCCO"): setnet(b, V3)
        elif n == "MGTAVCC": setnet(b, AVCC)
        elif n == "MGTAVTT": setnet(b, AVTT)

    # ---- FPGA part: units = banks ---------------------------------------------
    unit_of = {"216": 1, "0": 2, "14": 3, "15": 4, "34": 5}
    pins = []
    for b, n, bank in balls:
        if n in ("GND",) or n.startswith("VCC") or n.startswith("MGTAV"):
            unit = 6
        else:
            unit = unit_of.get(bank, 6)
        side = "L" if (n.startswith("MGTPRX") or n.startswith("MGTREF") or n.startswith("IO_") and n.endswith(("_15", "_34")) and "P_" in n) else "R"
        if unit == 6:
            side = "L" if n in ("GND",) else "R"
        pins.append(Pin(b, n, fpga_net.get(b), unit=unit, side=side))
    # stable ordering inside each unit: by name
    pins.sort(key=lambda p: (p.unit, p.side, p.name))
    d.add(Part("U1", "XC7A50T-2CSG325I", "XC7A50T-CSG325", fp("Xilinx_CSG325"), pins,
               mpn="XC7A50T-2CSG325I", description="AMD Artix-7 FPGA, 52k LUT, 4 GTP, CSG325 (35T/100T drop-in)",
               sheet="fpga_io", place=(0, 24.0, 180, "F")))
    d.parts[-1].zone = "fixed"

    # ---- M.2 connector ----------------------------------------------------------
    m2 = {1: GND, 2: V3IN, 3: GND, 4: V3IN, 5: "PCIE_RX3_N", 7: "PCIE_RX3_P", 9: GND, 11: "PCIE_TX3_N_C", 13: "PCIE_TX3_P_C",
          12: V3IN, 14: V3IN, 15: GND, 16: V3IN, 17: "PCIE_RX2_N", 18: V3IN, 19: "PCIE_RX2_P", 21: GND,
          23: "PCIE_TX2_N_C", 25: "PCIE_TX2_P_C", 27: GND, 29: "PCIE_RX1_N", 31: "PCIE_RX1_P", 33: GND,
          35: "PCIE_TX1_N_C", 37: "PCIE_TX1_P_C", 39: GND, 41: "PCIE_RX0_N", 43: "PCIE_RX0_P", 45: GND,
          47: "PCIE_TX0_N_C", 49: "PCIE_TX0_P_C", 50: "PCIE_PERST_N", 51: GND, 52: "PCIE_CLKREQ_N",
          53: "PCIE_REFCLK_N_C", 55: "PCIE_REFCLK_P_C", 57: GND, 70: V3IN, 71: GND, 72: V3IN, 73: GND, 74: V3IN, 75: GND}
    # NOTE on pin naming: table 48 is the platform (host) side. Host PETx (its
    # transmitter) lands on our receiver: pins 5/7 = PERn3/PERp3 are the host's
    # receive, i.e. OUR transmit. Mapping used here (host pin -> our net):
    #   PETp/n = host TX -> PCIE_RXx ; PERp/n = host RX -> PCIE_TXx (via AC caps)
    # Pin 5 PERn3, 7 PERp3 -> our TX3; 11 PETn3, 13 PETp3 -> our RX3, etc.
    m2.update({5: "PCIE_TX3_N_C", 7: "PCIE_TX3_P_C", 11: "PCIE_RX3_N", 13: "PCIE_RX3_P",
               17: "PCIE_TX2_N_C", 19: "PCIE_TX2_P_C", 23: "PCIE_RX2_N", 25: "PCIE_RX2_P",
               29: "PCIE_TX1_N_C", 31: "PCIE_TX1_P_C", 35: "PCIE_RX1_N", 37: "PCIE_RX1_P",
               41: "PCIE_TX0_N_C", 43: "PCIE_TX0_P_C", 47: "PCIE_RX0_N", 49: "PCIE_RX0_P"})
    names = {5: "PERn3", 7: "PERp3", 11: "PETn3", 13: "PETp3", 17: "PERn2", 19: "PERp2", 23: "PETn2", 25: "PETp2",
             29: "PERn1", 31: "PERp1", 35: "PETn1", 37: "PETp1", 41: "PERn0", 43: "PERp0", 47: "PETn0", 49: "PETp0",
             50: "PERST#", 52: "CLKREQ#", 53: "REFCLKn", 55: "REFCLKp", 54: "PEWAKE#", 10: "DAS/DSS#", 38: "DEVSLP",
             68: "SUSCLK", 69: "PEDET", 40: "SMB_CLK", 42: "SMB_DATA", 44: "ALERT#", 56: "MFG_DATA", 58: "MFG_CLK"}
    m2pins = []
    for n in range(1, 76):
        if 59 <= n <= 66:
            continue
        net = m2.get(n)
        name = names.get(n) or ("GND" if net == GND else "3.3V" if net == V3IN else "NC")
        m2pins.append(Pin(str(n), f"{n}_{name}", net, side="L" if n % 2 else "R"))
    d.add(Part("J1", "M.2 2280 key M", "M2_Edge_KeyM", fp("M2_Edge_2280_KeyM"), m2pins,
               description="M.2 card edge, 2280, key M (PCIe x4 + 3.3 V)", sheet="m2", place=(0, 0, 0, "F")))
    d.parts[-1].zone = "fixed"

    # PCIe AC coupling on our transmit pairs (card side per PCIe base spec), and on REFCLK.
    # Each capacitor sits in line with its finger (pin n odd at x = 9.25 - (n-1)/4),
    # pads along y so the trace runs straight through. Two 0402s do not fit
    # side by side at the 0.5 mm finger pitch, so each capacitor is set 0.4 mm
    # outward from its finger: P and N jog by the same amount and stay matched.
    from footprints import M2_PIN1_X
    cap_pins = {("TX3", "N"): 5, ("TX3", "P"): 7, ("TX2", "N"): 17, ("TX2", "P"): 19, ("TX1", "N"): 29, ("TX1", "P"): 31,
                ("TX0", "N"): 41, ("TX0", "P"): 43, ("REFCLK", "N"): 53, ("REFCLK", "P"): 55}
    for lane in ("TX0", "TX1", "TX2", "TX3", "REFCLK"):
        for pol in ("P", "N"):
            x = M2_PIN1_X - (cap_pins[(lane, pol)] - 1) / 4 + (-0.4 if pol == "P" else 0.4)   # P finger is left of N
            C(d, "100n", f"PCIE_{lane}_{pol}", f"PCIE_{lane}_{pol}_C", "m2", "GRM155R71C104KA88D", voltage="16V",
              place=(x, 6.0, 270, "F"))
            d.parts[-1].zone = "fixed"
    R(d, "0R", "PCIE_CLKREQ_N", GND, "m2", zone="pcie")         # always request the clock
    R(d, "10k", "PCIE_PERST_N", V3, "m2", zone="pcie")         # keep reset asserted if host floats it
    R(d, "100R", "MGTRREF", GND, "m2", mpn="RC0402FR-07100RL", zone="pcie")

    # ---- config / JTAG / clock / LEDs ----------------------------------------------
    ic(d, "U2", "W25Q128JVPIQ", "W25Q128JV", fp("WSON-8_6x5mm_P1.27mm"),
       [(1, "/CS", "QSPI_CS_N", "L"), (2, "DO/IO1", "QSPI_IO1", "L"), (3, "/WP/IO2", "QSPI_IO2", "L"), (4, "GND", GND, "L"),
        (5, "DI/IO0", "QSPI_IO0", "R"), (6, "CLK", "QSPI_CLK", "R"), (7, "/HOLD/IO3", "QSPI_IO3", "R"), (8, "VCC", V3, "R"), (9, "PAD", GND, "R")],
       "fpga_io", "W25Q128JVPIQ", "128 Mbit QSPI configuration flash, WSON-8")
    C(d, "100n", V3, GND, "fpga_io")
    R(d, "4k7", "QSPI_CS_N", V3, "fpga_io")
    R(d, "4k7", "CFG_M0", V3, "fpga_io")           # M[2:0] = 001: master SPI
    R(d, "4k7", "PUDC_B", V3, "fpga_io")         # internal pull-ups off during config
    R(d, "4k7", "DONE", V3, "fpga_io")
    R(d, "4k7", "INIT_B", V3, "fpga_io")
    R(d, "4k7", "PROGRAM_B", V3, "fpga_io")
    ic(d, "J2", "TC2050 JTAG", "TagConnect_JTAG", fp("TagConnect_TC2050-NL"),
       [(1, "VREF", V3, "L"), (2, "TMS", "JTAG_TMS", "L"), (3, "GND", GND, "L"), (4, "TCK", "JTAG_TCK", "L"), (5, "GND", GND, "L"),
        (6, "TDO", "JTAG_TDO", "R"), (7, "TDI", "JTAG_TDI", "R"), (8, "NC", None, "R"), (9, "NC", None, "R"), (10, "GND", GND, "R")],
       "fpga_io", "", "Tag-Connect TC2050 JTAG pads, no part fitted (cable TC2050-IDC-NL; Xilinx: VREF, TMS, GND, TCK, GND, TDO, TDI)",
       place=(0, 44.3, 0, "F"))
    d.parts[-1].zone = "fixed"   # its alignment holes go through the board: keep it in its own band
    ic(d, "X1", "100 MHz 3.3V", "OSC_2520", fp("Oscillator_2520_4pin"),
       [(1, "EN/NC", None, "L"), (2, "GND", GND, "L"), (3, "OUT", "CLK100M", "R"), (4, "VDD", V3, "R")],
       "fpga_io", "ECS-2520MV-100-CN-TR", "100 MHz CMOS oscillator, 2.5x2.0 mm, 3.3 V")
    C(d, "100n", V3, GND, "fpga_io")
    for i in range(4):   # on the back, where there is room (a card in a slot hides both sides anyway)
        LED(d, "green", f"LED{i}_N", f"LED{i}_A", "fpga_io", "19-217/GHC-YR1S2/3T", zone="leds", side="B")
        R(d, "1k", f"LED{i}_A", V3, "fpga_io", zone="leds", side="B")

    # ---- FPGA decoupling (per UG483 guidance, scaled for the 50T) ---------------------
    # One placement zone per rail (see pcb.ZONES) so each capacitor sits over
    # its own plane and the fan-out can drop a via straight into it.
    def decouple(net, zone, items, sheet="fpga_pwr"):
        for value, size, n, mpn in items:
            for k in range(n):
                C(d, value, net, GND, sheet, mpn, size=size, zone=zone, side="B")
    decouple(V1,   "decap_1v0",  [("4u7", "0402", 2, "GRM155R60J475ME47D"), ("470n", "0402", 4, "GRM155R61A474KE15D")])
    C(d, "47u", V1, GND, "fpga_pwr", "GRM21BR60J476ME15L", size="0805", zone="power_b", side="B")   # bulk, near the buck (the 1.0 V strip is too narrow for it beside the BGA)
    decouple(V18,  "decap_1v8",  [("47u", "0805", 1, "GRM21BR60J476ME15L"), ("4u7", "0402", 1, "GRM155R60J475ME47D"), ("470n", "0402", 2, "GRM155R61A474KE15D")])
    decouple(V3,   "decap_3v3",  [("47u", "0805", 1, "GRM21BR60J476ME15L"), ("4u7", "0402", 4, "GRM155R60J475ME47D"), ("470n", "0402", 4, "GRM155R61A474KE15D")])
    decouple(AVCC, "decap_avcc", [("4u7", "0402", 2, "GRM155R60J475ME47D"), ("100n", "0402", 3, "GRM155R71C104KA88D")])
    decouple(AVTT, "decap_avtt", [("4u7", "0402", 2, "GRM155R60J475ME47D"), ("100n", "0402", 3, "GRM155R71C104KA88D")])
    FB(d, "600R@100MHz", V18, "VCCADC", "fpga_pwr", "BLM15AG601SN1D", zone="decap_1v8", side="B")
    C(d, "100n", "VCCADC", GND, "fpga_pwr", zone="decap_1v8", side="B")

    # ---- power supplies -----------------------------------------------------------
    # VCCINT 1.0 V: TPS62823, FB = 0.6 V: R1/R2 = (1.0-0.6)/0.6 -> 68k / 100k
    ic(d, "U3", "TPS62823DLCR", "TPS62823", fp("VSON-8_2x1.5mm_P0.5mm"),
       [(1, "EN", V3IN, "L"), (2, "FB", "FB_1V0", "L"), (3, "AGND", GND, "L"), (4, "NC", None, "L"),
        (5, "PGND", GND, "R"), (6, "SW", "SW_1V0", "R"), (7, "VIN", V3IN, "R"), (8, "PG", "PG_1V0", "R")],
       "power", "TPS62823DLCR", "3 A synchronous buck, 1.0 V VCCINT/VCCBRAM")
    C(d, "10u", V3IN, GND, "power", "GRM188R61A106KE69D", size="0603", voltage="10V")
    L(d, "470nH", "SW_1V0", V1, "power", "TFM201610ALMA-R47MTAA")
    C(d, "22u", V1, GND, "power", "GRM188R60J226MEA0D", size="0603", voltage="6.3V")
    R(d, "68k", V1, "FB_1V0", "power")
    R(d, "100k", "FB_1V0", GND, "power")
    R(d, "100k", "PG_1V0", V3IN, "power")
    # VCCAUX 1.8 V: TLV62569, enabled by the 1.0 V power-good. FB 0.6 V: R1/R2 = 2 -> 200k / 100k
    ic(d, "U4", "TLV62569DBVR", "TLV62569", fp("SOT-23-5"),
       [(1, "EN", "PG_1V0", "L"), (2, "GND", GND, "L"), (3, "SW", "SW_1V8", "L"), (4, "VIN", V3IN, "R"), (5, "FB", "FB_1V8", "R")],
       "power", "TLV62569DBVR", "2 A synchronous buck, 1.8 V VCCAUX")
    C(d, "10u", V3IN, GND, "power", "GRM188R61A106KE69D", size="0603", voltage="10V")
    L(d, "1uH", "SW_1V8", V18, "power", "TFM201610ALMA-1R0MTAA")
    C(d, "22u", V18, GND, "power", "GRM188R60J226MEA0D", size="0603", voltage="6.3V")
    R(d, "200k", V18, "FB_1V8", "power")
    R(d, "100k", "FB_1V8", GND, "power")
    # MGT rails from 1.8 V: 1.0 V and 1.2 V fixed LDOs
    ic(d, "U5", "TLV75510PDBVR", "TLV755P", fp("SOT-23-5"),
       [(1, "IN", V18, "L"), (2, "GND", GND, "L"), (3, "EN", V18, "L"), (4, "NC", None, "R"), (5, "OUT", AVCC, "R")],
       "power", "TLV75510PDBVR", "500 mA LDO, 1.0 V MGTAVCC")
    C(d, "1u", V18, GND, "power", voltage="10V")
    C(d, "1u", AVCC, GND, "power", voltage="10V")
    ic(d, "U6", "TLV75512PDBVR", "TLV755P", fp("SOT-23-5"),
       [(1, "IN", V18, "L"), (2, "GND", GND, "L"), (3, "EN", V18, "L"), (4, "NC", None, "R"), (5, "OUT", AVTT, "R")],
       "power", "TLV75512PDBVR", "500 mA LDO, 1.2 V MGTAVTT")
    C(d, "1u", V18, GND, "power", voltage="10V")
    C(d, "1u", AVTT, GND, "power", voltage="10V")
    # VCCO 3.3 V: load switch enabled once 1.8 V is up (RC delay), slew limited
    ic(d, "U7", "TPS22918DBVR", "TPS22918", fp("SOT-23-6"),
       [(1, "VIN", V3IN, "L"), (2, "GND", GND, "L"), (3, "ON", "EN_3V3", "L"), (4, "CT", "CT_3V3", "R"), (5, "QOD", V3, "R"), (6, "VOUT", V3, "R")],
       "power", "TPS22918DBVR", "2 A load switch, sequenced 3.3 V for VCCO/flash/CAN logic")
    R(d, "100k", V18, "EN_3V3", "power")
    C(d, "100n", "EN_3V3", GND, "power")          # ~10 ms delay after 1.8 V
    C(d, "1n", "CT_3V3", GND, "power")           # slew ~ 1 ms
    C(d, "10u", V3, GND, "power", "GRM188R61A106KE69D", size="0603", voltage="10V")
    LED(d, "green", "PWR_LED_K", V3, "power", "19-217/GHC-YR1S2/3T")
    R(d, "1k", "PWR_LED_K", GND, "power")
    # 5 V for the CAN transceivers: TPS61023 boost, FB 0.6 V: R1/R2 = (5-0.6)/0.6 = 7.33 -> 732k / 100k
    ic(d, "U8", "TPS61023DRLR", "TPS61023", fp("SOT-563"),
       [(1, "FB", "FB_5V", "L"), (2, "EN", V3, "L"), (3, "VIN", V3IN, "L"), (4, "GND", GND, "R"), (5, "SW", "SW_5V", "R"), (6, "VOUT", V5CAN, "R")],
       "power", "TPS61023DRLR", "Boost 3.3 V -> 5 V for the CAN transceivers (enabled with the 3.3 V rail)")
    C(d, "10u", V3IN, GND, "power", "GRM188R61A106KE69D", size="0603", voltage="10V")
    L(d, "1uH", V3IN, "SW_5V", "power", "TFM201610ALMA-1R0MTAA")
    C(d, "10u", V5CAN, GND, "power", "GRM188R61A106KE69D", size="0603", voltage="10V")
    R(d, "732k", V5CAN, "FB_5V", "power")
    R(d, "100k", "FB_5V", GND, "power")

    # ---- CAN FD transceivers --------------------------------------------------------
    conn = []
    for i in range(4):
        x = -8.0 + i * 5.3
        ic(d, f"U{10 + i}", "MCP2562FD", "MCP2562FD", fp("DFN-8_3x3mm_P0.65mm"),
           [(1, "TXD", f"CAN{i}_TXD", "L"), (2, "VSS", GND, "L"), (3, "VDD", V5CAN, "L"), (4, "RXD", f"CAN{i}_RXD", "L"),
            (5, "VIO", V3, "R"), (6, "CANL", f"CAN{i}_L", "R"), (7, "CANH", f"CAN{i}_H", "R"), (8, "STBY", f"CAN{i}_STBY", "R"), (9, "PAD", GND, "R")],
           "can", "MCP2562FDT-E/MF", f"CAN FD transceiver bus {i}, 8 Mbit/s, 5 V with 3.3 V I/O")
        C(d, "100n", V5CAN, GND, "can")
        C(d, "100n", V3, GND, "can")
        # bus protection and optional termination (solder jumper)
        ic(d, f"D{10 + i}", "PESD2CAN", "PESD2CAN", fp("SOT-23"),
           [(1, "I/O1", f"CAN{i}_H", "L"), (2, "I/O2", f"CAN{i}_L", "L"), (3, "GND", GND, "R")],
           "can", "PESD2CANUX", "CAN bus ESD protection")
        R(d, "120R", f"CAN{i}_H", f"CAN{i}_TERM", "can", "RC0402FR-07120RL")
        R(d, "0R", f"CAN{i}_TERM", f"CAN{i}_L", "can")
        d.parts[-1].dnp = True
        d.parts[-1].description += " (DNP: fit for bus-end termination)"
        conn += [(3 * i + 1, f"CAN{i}_H", f"CAN{i}_H"), (3 * i + 2, f"CAN{i}_L", f"CAN{i}_L"), (3 * i + 3, "GND", GND)]
    # Two 6-way headers at the far end, either side of the mount notch (a
    # wider header would collide with the notch): J3 buses 0+1, J4 buses 2+3,
    # each H, L, GND, H, L, GND. Cable exits off the end of the card.
    for ref, buses, x in (("J3", (0, 1), -6.95), ("J4", (2, 3), 6.95)):
        jp = []
        n = 1
        for b in buses:
            for name, net in ((f"CAN{b}_H", f"CAN{b}_H"), (f"CAN{b}_L", f"CAN{b}_L"), ("GND", GND)):
                jp.append(Pin(str(n), name, net, side="L" if n <= 3 else "R")); n += 1
        jp.append(Pin("MP", "MP", GND, side="R"))
        d.add(Part(ref, "DF52-6S-0.8H", "DF52_6", fp("Hirose_DF52-6S-0.8H"), jp,
                   mpn="DF52-6S-0.8H(21)", description=f"CAN buses {buses[0]} and {buses[1]}: H, L, GND each; 0.8 mm wire-to-board, 1.5 mm tall",
                   sheet="can", place=(x, 77.5, 180, "F")))
        d.parts[-1].zone = "fixed"
    # Feedback dividers, pull-ups and CAN terminations go on the back, which is
    # empty beyond the decoupling; this keeps the front rows short enough to
    # leave routing corridors along both edges (see pcb.ZONES).
    for p in d.parts:
        if p.zone in ("power", "can") and p.footprint == fp("R_0402"):
            p.zone = p.zone + "_b"
            p.place = (0, 0, 0, "B")
    return d

if __name__ == "__main__":
    import os
    d = build(os.path.join(os.path.dirname(__file__), "data", "xc7a50tcsg325pkg.txt"))
    print(len(d.parts), "parts,", len(d.nets()), "nets")
    print("single-pin nets:", d.check())
