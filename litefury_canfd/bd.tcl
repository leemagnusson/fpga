# Block design for the LiteFury CAN FD card. Sourced by go.tcl inside an open
# project that already has the RTL files and the CTU CAN FD IP repository.
#
#   host <-PCIe x4 Gen1-> axi_pcie_0 --M_AXI--> smartconnect --+--> misc_regs (BAR0)
#                                                               +--> can_wrap_bd (AXI-Lite to APB) --> CTU CAN FD (BAR1)
#   200 MHz sys_clk -> clk_wiz -> 80 MHz CAN/APB clock
#   CAN irq -> irq_bridge -> axi_pcie INTX_MSI_Request

# Newest version of an IP in the catalog.
proc ipv {name} {
    set defs [get_ipdefs -all -filter "NAME == $name"]
    if {[llength $defs] == 0} { error "IP $name not found in catalog" }
    return [lindex [lsort -dictionary $defs] end]
}

create_bd_design canfd

# ---- external ports -------------------------------------------------------
set pcie_mgt    [create_bd_intf_port -mode Master -vlnv xilinx.com:interface:pcie_7x_mgt_rtl:1.0 pcie_mgt]
set pcie_refclk [create_bd_intf_port -mode Slave  -vlnv xilinx.com:interface:diff_clock_rtl:1.0 pcie_refclk]
set_property CONFIG.FREQ_HZ 100000000 $pcie_refclk
set sys_clk     [create_bd_intf_port -mode Slave  -vlnv xilinx.com:interface:diff_clock_rtl:1.0 sys_clk]
set_property CONFIG.FREQ_HZ 200000000 $sys_clk
set perst [create_bd_port -dir I -type rst pcie_perst_n]
set_property CONFIG.POLARITY ACTIVE_LOW $perst
create_bd_port -dir O can_tx
create_bd_port -dir I can_rx
create_bd_port -dir O can_stby
create_bd_port -dir O -from 3 -to 0 leds

# ---- PCIe ------------------------------------------------------------------
set refclk_buf [create_bd_cell -type ip -vlnv [ipv util_ds_buf] pcie_refclk_buf]
set_property CONFIG.C_BUF_TYPE IBUFDSGTE $refclk_buf

set pcie [create_bd_cell -type ip -vlnv [ipv axi_pcie] axi_pcie_0]
set_property -dict [list \
    CONFIG.NO_OF_LANES {X4} \
    CONFIG.MAX_LINK_SPEED {2.5_GT/s} \
    CONFIG.PCIE_BLK_LOCN {X0Y0} \
    CONFIG.REF_CLK_FREQ {100_MHz} \
    CONFIG.XLNX_REF_BOARD {None} \
    CONFIG.VENDOR_ID $::pci_vendor_id \
    CONFIG.DEVICE_ID $::pci_device_id \
    CONFIG.REV_ID {0x01} \
    CONFIG.SUBSYSTEM_VENDOR_ID $::pci_vendor_id \
    CONFIG.SUBSYSTEM_ID $::pci_device_id \
    CONFIG.M_AXI_DATA_WIDTH {128} \
    CONFIG.S_AXI_DATA_WIDTH {128} \
    CONFIG.AXIBAR_NUM {1} \
    CONFIG.BAR0_ENABLED {true} CONFIG.BAR0_TYPE {Memory} CONFIG.BAR0_SCALE {Kilobytes} CONFIG.BAR0_SIZE {32} \
    CONFIG.PCIEBAR2AXIBAR_0 {0x00000000} \
    CONFIG.BAR1_ENABLED {true} CONFIG.BAR1_TYPE {Memory} CONFIG.BAR1_SCALE {Kilobytes} CONFIG.BAR1_SIZE {16} \
    CONFIG.PCIEBAR2AXIBAR_1 {0x00010000} \
    CONFIG.MSI_DECODE_ENABLED {true} \
    CONFIG.NUM_MSI_REQ {0} \
    CONFIG.INTERRUPT_PIN {true} \
] $pcie
# Class code 0x0C09 = serial bus controller, CANbus. Not all IP versions let
# this be set directly; it is cosmetic, so ignore failure.
catch { set_property -dict [list CONFIG.ENABLE_CLASS_CODE {true} CONFIG.CLASS_CODE {0x0C0900}] $pcie }

connect_bd_intf_net $pcie_refclk [get_bd_intf_pins $refclk_buf/CLK_IN_D]
connect_bd_net [get_bd_pins $refclk_buf/IBUF_OUT] [get_bd_pins $pcie/REFCLK]
connect_bd_intf_net $pcie_mgt [get_bd_intf_pins $pcie/pcie_7x_mgt]

# Reset for the PCIe/AXI clock domain: released once the bridge's MMCM locks.
set rst_pcie [create_bd_cell -type ip -vlnv [ipv proc_sys_reset] rst_pcie]
connect_bd_net [get_bd_pins $pcie/axi_aclk_out] [get_bd_pins $rst_pcie/slowest_sync_clk]
connect_bd_net $perst [get_bd_pins $rst_pcie/ext_reset_in]
connect_bd_net [get_bd_pins $pcie/mmcm_lock] [get_bd_pins $rst_pcie/dcm_locked]
connect_bd_net [get_bd_pins $rst_pcie/peripheral_aresetn] [get_bd_pins $pcie/axi_aresetn]

# ---- CAN clock: 200 MHz on-board oscillator -> 80 MHz ------------------------
# 80 MHz makes both 1 Mbit/s (80 tq) and 8 Mbit/s (10 tq) integer divisions.
set clk [create_bd_cell -type ip -vlnv [ipv clk_wiz] clk_wiz_0]
set_property -dict [list \
    CONFIG.PRIM_SOURCE {Differential_clock_capable_pin} \
    CONFIG.PRIM_IN_FREQ {200.000} \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {80.000} \
    CONFIG.USE_LOCKED {true} \
    CONFIG.USE_RESET {false} \
] $clk
connect_bd_intf_net $sys_clk [get_bd_intf_pins $clk/CLK_IN1_D]

set rst_can [create_bd_cell -type ip -vlnv [ipv proc_sys_reset] rst_can]
connect_bd_net [get_bd_pins $clk/clk_out1] [get_bd_pins $rst_can/slowest_sync_clk]
connect_bd_net $perst [get_bd_pins $rst_can/ext_reset_in]
connect_bd_net [get_bd_pins $clk/locked] [get_bd_pins $rst_can/dcm_locked]

# ---- AXI fabric ---------------------------------------------------------------
set smc [create_bd_cell -type ip -vlnv [ipv smartconnect] axi_smc]
set num_mi [expr {[info exists ::env(BD_SMOKE_TEST)] ? 1 : 2}]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI $num_mi CONFIG.NUM_CLKS {2}] $smc
connect_bd_intf_net [get_bd_intf_pins $pcie/M_AXI] [get_bd_intf_pins $smc/S00_AXI]
connect_bd_net [get_bd_pins $pcie/axi_aclk_out] [get_bd_pins $smc/aclk]
connect_bd_net [get_bd_pins $clk/clk_out1]     [get_bd_pins $smc/aclk1]
connect_bd_net [get_bd_pins $rst_pcie/peripheral_aresetn] [get_bd_pins $smc/aresetn]

# ---- BAR0: board registers ----------------------------------------------------
set misc [create_bd_cell -type module -reference misc_regs misc_regs_0]
connect_bd_intf_net [get_bd_intf_pins $smc/M00_AXI] [get_bd_intf_pins $misc/s_axi]
connect_bd_net [get_bd_pins $clk/clk_out1] [get_bd_pins $misc/s_axi_aclk]
connect_bd_net [get_bd_pins $rst_can/peripheral_aresetn] [get_bd_pins $misc/s_axi_aresetn]
connect_bd_net [get_bd_pins $pcie/user_link_up] [get_bd_pins $misc/link_up]
connect_bd_net [get_bd_pins $misc/leds] [get_bd_ports leds]

# ---- BAR1: CTU CAN FD core ---------------------------------------------------------
# rtl/can_wrap_bd.v presents an AXI4-Lite slave and bridges it to the core's
# APB4 port; rtl/can_wrap.vhd instantiates the core (library ctu_can_fd_rtl).
set zero [create_bd_cell -type ip -vlnv [ipv xlconstant] const_0]
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {0}] $zero
connect_bd_net [get_bd_pins $zero/dout] [get_bd_ports can_stby]

# BD_SMOKE_TEST in the environment builds everything except the CAN core, to
# check the PCIe side and constraints without the submodule present.
if {[info exists ::env(BD_SMOKE_TEST)]} {
    puts "BD_SMOKE_TEST set: leaving the CTU CAN FD core out"
    set can_irq_net [get_bd_pins $zero/dout]
} else {
    set can [create_bd_cell -type module -reference can_wrap_bd ctu_can_fd_0]
    connect_bd_intf_net [get_bd_intf_pins $smc/M01_AXI] [get_bd_intf_pins $can/s_axi]
    connect_bd_net [get_bd_pins $clk/clk_out1] [get_bd_pins $can/s_axi_aclk]
    connect_bd_net [get_bd_pins $rst_can/peripheral_aresetn] [get_bd_pins $can/s_axi_aresetn]
    connect_bd_net [get_bd_pins $misc/timestamp] [get_bd_pins $can/timestamp]
    connect_bd_net [get_bd_pins $can/can_tx] [get_bd_ports can_tx]
    connect_bd_net [get_bd_ports can_rx] [get_bd_pins $can/can_rx]
    set can_irq_net [get_bd_pins $can/irq]
}
connect_bd_net $can_irq_net [get_bd_pins $misc/can_irq]

# ---- interrupt ----------------------------------------------------------------
set irq [create_bd_cell -type module -reference irq_bridge irq_bridge_0]
connect_bd_net [get_bd_pins $pcie/axi_aclk_out] [get_bd_pins $irq/clk]
connect_bd_net [get_bd_pins $rst_pcie/peripheral_aresetn] [get_bd_pins $irq/resetn]
connect_bd_net $can_irq_net [get_bd_pins $irq/irq_in]
connect_bd_net [get_bd_pins $misc/irq_enable] [get_bd_pins $irq/irq_enable]
connect_bd_net [get_bd_pins $pcie/MSI_enable] [get_bd_pins $irq/msi_enable]
connect_bd_net [get_bd_pins $pcie/INTX_MSI_Grant] [get_bd_pins $irq/grant]
connect_bd_net [get_bd_pins $irq/req] [get_bd_pins $pcie/INTX_MSI_Request]
connect_bd_net [get_bd_pins $irq/msi_vector_num] [get_bd_pins $pcie/MSI_Vector_Num]

# ---- address map: BAR0 -> 0x0000_0000 (32 KB), BAR1 -> 0x0001_0000 (16 KB) ----------
# (axi_pcie maps PCIe BAR0/BAR1 to these AXI addresses, see PCIEBAR2AXIBAR_*)
set m_axi [get_bd_addr_spaces $pcie/M_AXI]
create_bd_addr_seg -range 32K -offset 0x00000000 $m_axi [get_bd_addr_segs $misc/s_axi/reg0] SEG_misc_regs
if {![info exists ::env(BD_SMOKE_TEST)]} {
    create_bd_addr_seg -range 16K -offset 0x00010000 $m_axi [get_bd_addr_segs $can/s_axi/reg0] SEG_ctu_can_fd
}

regenerate_bd_layout
validate_bd_design
save_bd_design
