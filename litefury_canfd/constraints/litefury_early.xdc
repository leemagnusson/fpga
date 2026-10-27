# Processed before the PCIe IP's own constraints (PROCESSING_ORDER EARLY).
# GT channel placement and MGT pins for the LiteFury's M.2 PCIe x4 link, as
# used by RHS Research's sample project (lane order is not physical order).
set_property LOC GTPE2_CHANNEL_X0Y6 [get_cells -hierarchical -regexp {.*pipe_lane\[0\]\.gt_wrapper_i/gtp_channel\.gtpe2_channel_i}]
set_property LOC GTPE2_CHANNEL_X0Y4 [get_cells -hierarchical -regexp {.*pipe_lane\[1\]\.gt_wrapper_i/gtp_channel\.gtpe2_channel_i}]
set_property LOC GTPE2_CHANNEL_X0Y5 [get_cells -hierarchical -regexp {.*pipe_lane\[2\]\.gt_wrapper_i/gtp_channel\.gtpe2_channel_i}]
set_property LOC GTPE2_CHANNEL_X0Y7 [get_cells -hierarchical -regexp {.*pipe_lane\[3\]\.gt_wrapper_i/gtp_channel\.gtpe2_channel_i}]

set_property PACKAGE_PIN A10 [get_ports {pcie_mgt_rxn[0]}]
set_property PACKAGE_PIN B10 [get_ports {pcie_mgt_rxp[0]}]
set_property PACKAGE_PIN A6  [get_ports {pcie_mgt_txn[0]}]
set_property PACKAGE_PIN B6  [get_ports {pcie_mgt_txp[0]}]
set_property PACKAGE_PIN A8  [get_ports {pcie_mgt_rxn[1]}]
set_property PACKAGE_PIN B8  [get_ports {pcie_mgt_rxp[1]}]
set_property PACKAGE_PIN A4  [get_ports {pcie_mgt_txn[1]}]
set_property PACKAGE_PIN B4  [get_ports {pcie_mgt_txp[1]}]
set_property PACKAGE_PIN C11 [get_ports {pcie_mgt_rxn[2]}]
set_property PACKAGE_PIN D11 [get_ports {pcie_mgt_rxp[2]}]
set_property PACKAGE_PIN C5  [get_ports {pcie_mgt_txn[2]}]
set_property PACKAGE_PIN D5  [get_ports {pcie_mgt_txp[2]}]
set_property PACKAGE_PIN C9  [get_ports {pcie_mgt_rxn[3]}]
set_property PACKAGE_PIN D9  [get_ports {pcie_mgt_rxp[3]}]
set_property PACKAGE_PIN C7  [get_ports {pcie_mgt_txn[3]}]
set_property PACKAGE_PIN D7  [get_ports {pcie_mgt_txp[3]}]

# 100 MHz PCIe reference clock from the M.2 connector
set_property PACKAGE_PIN F6 [get_ports pcie_refclk_clk_p]
set_property PACKAGE_PIN E6 [get_ports pcie_refclk_clk_n]
create_clock -period 10.000 -name pcie_refclk [get_ports pcie_refclk_clk_p]
