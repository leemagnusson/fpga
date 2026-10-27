-- Thin wrapper around the CTU CAN FD core's APB top level so it can be used
-- as a block-design module reference. The core's own Vivado IP package
-- (src/component.xml) is out of date relative to the RTL (port and generic
-- names differ), so the RTL is compiled into library ctu_can_fd_rtl and
-- instantiated here instead.
--
-- Configuration: 256-word RX buffer, 4 TXT buffers (what the Linux driver
-- expects), no hardware filters, traffic counters on, test registers off.

library ieee;
use ieee.std_logic_1164.all;

library ctu_can_fd_rtl;

entity can_wrap is
    port (
        aclk          : in  std_logic;
        arstn         : in  std_logic;

        s_apb_paddr   : in  std_logic_vector(31 downto 0);
        s_apb_psel    : in  std_logic;
        s_apb_penable : in  std_logic;
        s_apb_pwrite  : in  std_logic;
        s_apb_pwdata  : in  std_logic_vector(31 downto 0);
        s_apb_pstrb   : in  std_logic_vector(3 downto 0);
        s_apb_pprot   : in  std_logic_vector(2 downto 0);
        s_apb_pready  : out std_logic;
        s_apb_prdata  : out std_logic_vector(31 downto 0);
        s_apb_pslverr : out std_logic;

        timestamp     : in  std_logic_vector(63 downto 0);
        irq           : out std_logic;
        can_tx        : out std_logic;
        can_rx        : in  std_logic
    );

    attribute X_INTERFACE_INFO      : string;
    attribute X_INTERFACE_PARAMETER : string;
    attribute X_INTERFACE_INFO of aclk  : signal is "xilinx.com:signal:clock:1.0 aclk CLK";
    attribute X_INTERFACE_PARAMETER of aclk : signal is "ASSOCIATED_BUSIF s_apb, ASSOCIATED_RESET arstn";
    attribute X_INTERFACE_INFO of arstn : signal is "xilinx.com:signal:reset:1.0 arstn RST";
    attribute X_INTERFACE_PARAMETER of arstn : signal is "POLARITY ACTIVE_LOW";
    attribute X_INTERFACE_INFO of s_apb_paddr   : signal is "xilinx.com:interface:apb:1.0 s_apb PADDR";
    attribute X_INTERFACE_INFO of s_apb_psel    : signal is "xilinx.com:interface:apb:1.0 s_apb PSEL";
    attribute X_INTERFACE_INFO of s_apb_penable : signal is "xilinx.com:interface:apb:1.0 s_apb PENABLE";
    attribute X_INTERFACE_INFO of s_apb_pwrite  : signal is "xilinx.com:interface:apb:1.0 s_apb PWRITE";
    attribute X_INTERFACE_INFO of s_apb_pwdata  : signal is "xilinx.com:interface:apb:1.0 s_apb PWDATA";
    attribute X_INTERFACE_INFO of s_apb_pstrb   : signal is "xilinx.com:interface:apb:1.0 s_apb PSTRB";
    attribute X_INTERFACE_INFO of s_apb_pprot   : signal is "xilinx.com:interface:apb:1.0 s_apb PPROT";
    attribute X_INTERFACE_INFO of s_apb_pready  : signal is "xilinx.com:interface:apb:1.0 s_apb PREADY";
    attribute X_INTERFACE_INFO of s_apb_prdata  : signal is "xilinx.com:interface:apb:1.0 s_apb PRDATA";
    attribute X_INTERFACE_INFO of s_apb_pslverr : signal is "xilinx.com:interface:apb:1.0 s_apb PSLVERR";
    attribute X_INTERFACE_INFO of irq : signal is "xilinx.com:signal:interrupt:1.0 irq INTERRUPT";
    attribute X_INTERFACE_PARAMETER of irq : signal is "SENSITIVITY LEVEL_HIGH";
end entity can_wrap;

architecture rtl of can_wrap is
begin
    core : entity ctu_can_fd_rtl.ctu_can_fd_top_apb
        generic map (
            G_RX_BUF_SIZE     => 256,
            G_TXT_BUF_COUNT   => 4,
            G_FILT_A_EN       => false,
            G_FILT_B_EN       => false,
            G_FILT_C_EN       => false,
            G_FILT_RANGE_EN   => false,
            G_TEST_REGS_EN    => false,
            G_TRAFFIC_CTRS_EN => true,
            G_PARITY_EN       => false,
            G_ACTIVE_TS_BITS  => 63,
            G_RESET_BUF_RAMS  => false,
            G_TECHNOLOGY      => 1          -- C_TECH_FPGA
        )
        port map (
            aclk          => aclk,
            arstn         => arstn,
            scan_mode     => '0',
            rst_n_out     => open,
            irq           => irq,
            can_tx        => can_tx,
            can_rx        => can_rx,
            timestamp     => timestamp,
            s_apb_paddr   => s_apb_paddr,
            s_apb_penable => s_apb_penable,
            s_apb_pprot   => s_apb_pprot,
            s_apb_prdata  => s_apb_prdata,
            s_apb_pready  => s_apb_pready,
            s_apb_psel    => s_apb_psel,
            s_apb_pslverr => s_apb_pslverr,
            s_apb_pstrb   => s_apb_pstrb,
            s_apb_pwdata  => s_apb_pwdata,
            s_apb_pwrite  => s_apb_pwrite
        );
end architecture rtl;
