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
    CONFIG.MAX_LINK_SPEED $::pcie_link_speed \
    CONFIG.PCIE_BLK_LOCN {X0Y0} \
    CONFIG.REF_CLK_FREQ {100_MHz} \
    CONFIG.XLNX_REF_BOARD {None} \
    CONFIG.VENDOR_ID $::pci_vendor_id \
    CONFIG.DEVICE_ID $::pci_device_id \
    CONFIG.REV_ID {0x01} \
    CONFIG.SUBSYSTEM_VENDOR_ID $::pci_vendor_id \
    CONFIG.SUBSYSTEM_ID $::pci_device_id \
    CONFIG.M_AXI_DATA_WIDTH $::axi_data_width \
    CONFIG.S_AXI_DATA_WIDTH $::axi_data_width \
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

# ---- optional debug: DEBUG_ILA=1 adds an ILA (free-licence flavour) -------------
# The BASIC licence allows one ILA with at most 5 probe ports and no System ILA
# on an interface, so rtl/debug/axi_tap_*.v monitor the AXI links and bundle
# them into a few wide vectors. The ILA runs on axi_aclk (125 MHz) and samples
# the 80 MHz AXI-Lite side asynchronously, which is fine for debugging since
# every 80 MHz state lasts longer than one 125 MHz sample.
#   probe0 tap_pcie ctl (bit 0 = arvalid)   probe1 tap_pcie araddr
#   probe2 tap_pcie rdata                   probe3 {tap_can1 ctl, tap_can0 ctl, stat[4:0]}
#   probe4 {tap_can1 rdata, tap_can0 rdata} stat = {rst_pcie_n, mmcm_lock, link_up, clk_locked, rst_can_n}
# Probe file: build/canfd.runs/impl_1/canfd_wrapper.ltx.
if {[info exists ::env(DEBUG_ILA)]} {
    puts "DEBUG_ILA set: adding ILA"
    set tap_p [create_bd_cell -type module -reference axi_tap_mm tap_pcie]
    connect_bd_intf_net -intf_net [get_bd_intf_nets -of_objects [get_bd_intf_pins $pcie/M_AXI]] \
        [get_bd_intf_pins $pcie/M_AXI] [get_bd_intf_pins $tap_p/s_axi]
    connect_bd_net [get_bd_pins $pcie/axi_aclk_out] [get_bd_pins $tap_p/s_axi_aclk]
    set stat [create_bd_cell -type ip -vlnv [ipv xlconcat] dbg_stat]
    set_property CONFIG.NUM_PORTS 5 $stat
    connect_bd_net [get_bd_pins $rst_can/peripheral_aresetn]  [get_bd_pins $stat/In0]
    connect_bd_net [get_bd_pins $clk/locked]                  [get_bd_pins $stat/In1]
    connect_bd_net [get_bd_pins $pcie/user_link_up]           [get_bd_pins $stat/In2]
    connect_bd_net [get_bd_pins $pcie/mmcm_lock]              [get_bd_pins $stat/In3]
    connect_bd_net [get_bd_pins $rst_pcie/peripheral_aresetn] [get_bd_pins $stat/In4]
    set cctl [create_bd_cell -type ip -vlnv [ipv xlconcat] dbg_can_ctl]
    set_property CONFIG.NUM_PORTS 3 $cctl
    connect_bd_net [get_bd_pins $stat/dout] [get_bd_pins $cctl/In0]
    set crd [create_bd_cell -type ip -vlnv [ipv xlconcat] dbg_can_rd]
    set_property CONFIG.NUM_PORTS 2 $crd
    set i 0
    foreach mi [list M00_AXI M01_AXI] {
        set t [create_bd_cell -type module -reference axi_tap_lite tap_can$i]
        connect_bd_intf_net -intf_net [get_bd_intf_nets -of_objects [get_bd_intf_pins $smc/$mi]] \
            [get_bd_intf_pins $smc/$mi] [get_bd_intf_pins $t/s_axi]
        connect_bd_net [get_bd_pins $clk/clk_out1] [get_bd_pins $t/s_axi_aclk]
        connect_bd_net [get_bd_pins $t/ctl]   [get_bd_pins $cctl/In[expr {$i+1}]]
        connect_bd_net [get_bd_pins $t/rdata] [get_bd_pins $crd/In$i]
        incr i
    }
    set ila [create_bd_cell -type ip -vlnv [ipv ila] ila_dbg]
    set_property -dict [list CONFIG.C_MONITOR_TYPE {Native} CONFIG.C_NUM_OF_PROBES {5} \
        CONFIG.C_DATA_DEPTH {1024} CONFIG.C_PROBE0_WIDTH {61} CONFIG.C_PROBE1_WIDTH {32} \
        CONFIG.C_PROBE2_WIDTH {128} CONFIG.C_PROBE3_WIDTH {97} CONFIG.C_PROBE4_WIDTH {64}] $ila
    connect_bd_net [get_bd_pins $pcie/axi_aclk_out] [get_bd_pins $ila/clk]
    connect_bd_net [get_bd_pins $tap_p/ctl]    [get_bd_pins $ila/probe0]
    connect_bd_net [get_bd_pins $tap_p/araddr] [get_bd_pins $ila/probe1]
    connect_bd_net [get_bd_pins $tap_p/rdata]  [get_bd_pins $ila/probe2]
    connect_bd_net [get_bd_pins $cctl/dout]    [get_bd_pins $ila/probe3]
    connect_bd_net [get_bd_pins $crd/dout]     [get_bd_pins $ila/probe4]
}

regenerate_bd_layout
validate_bd_design
save_bd_design
