# LiteFury (XC7A100T-2L FGG484) pins for the CAN FD design.
# Processed after the IP constraints (PROCESSING_ORDER LATE).

## 200 MHz on-board oscillator (bank 15, LVDS)
set_property -dict {PACKAGE_PIN J19 IOSTANDARD LVDS_25} [get_ports sys_clk_clk_p]
set_property -dict {PACKAGE_PIN H19 IOSTANDARD LVDS_25} [get_ports sys_clk_clk_n]
# (the block design already creates the 200 MHz clock on sys_clk_clk_p)

## PCIe reset from the M.2 connector
set_property -dict {PACKAGE_PIN J1 IOSTANDARD LVCMOS33} [get_ports pcie_perst_n]
set_false_path -from [get_ports pcie_perst_n]

## User LEDs (active low: 681 ohm to 3.3 V)
set_property -dict {PACKAGE_PIN G3 IOSTANDARD LVCMOS33 PULLUP true DRIVE 8} [get_ports {leds[0]}]
set_property -dict {PACKAGE_PIN H3 IOSTANDARD LVCMOS33 PULLUP true DRIVE 8} [get_ports {leds[1]}]
set_property -dict {PACKAGE_PIN G4 IOSTANDARD LVCMOS33 PULLUP true DRIVE 8} [get_ports {leds[2]}]
set_property -dict {PACKAGE_PIN H4 IOSTANDARD LVCMOS33 PULLUP true DRIVE 8} [get_ports {leds[3]}]

## CAN transceiver on the I/O connector, bank 35 (3.3 V), the "AIO" pins:
##   AIO1_P (J5) -> transceiver TXD      AIO1_N (H5) <- transceiver RXD
##   AIO2_P (K2) -> transceiver STB/EN   (driven low = normal mode)
set_property -dict {PACKAGE_PIN J5 IOSTANDARD LVCMOS33 DRIVE 8 SLEW FAST} [get_ports can_tx]
set_property -dict {PACKAGE_PIN H5 IOSTANDARD LVCMOS33 PULLUP true}       [get_ports can_rx]
set_property -dict {PACKAGE_PIN K2 IOSTANDARD LVCMOS33 DRIVE 8}           [get_ports can_stby]
set_false_path -to   [get_ports {can_tx can_stby leds[*]}]
set_false_path -from [get_ports can_rx]

## Configuration: QSPI x4 from the on-board S25FL flash, external 90 MHz
## config clock, compressed bitstream (fast enough for PCIe to enumerate).
set_property BITSTREAM.CONFIG.OVERTEMPPOWERDOWN ENABLE [current_design]
set_property BITSTREAM.CONFIG.EXTMASTERCCLK_EN Div-1 [current_design]
set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 4 [current_design]
set_property CONFIG_MODE SPIx4 [current_design]
set_property BITSTREAM.CONFIG.SPI_FALL_EDGE YES [current_design]
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
set_property CFGBVS VCCO [current_design]
