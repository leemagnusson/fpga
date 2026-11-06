-- 250 MHz sampling clocks (0 and 90 degrees) from the board's 100 MHz.
-- Synthesis: MMCME2_BASE, VCO 1000 MHz, two outputs divided by 4, plus BUFGs.
-- Simulation (G_SIM): free-running clocks, no vendor library needed.
library ieee;
use ieee.std_logic_1164.all;

entity clk_gen is
    generic (
        G_SIM : boolean := false
    );
    port (
        clk_in   : in  std_logic;          -- 100 MHz
        clk_fast : out std_logic;          -- 250 MHz
        clk_f90  : out std_logic;          -- 250 MHz, +90 degrees
        locked   : out std_logic
    );
end entity clk_gen;

architecture rtl of clk_gen is
    signal fb, fb_b, c0, c1 : std_logic;
    signal sim_clk, sim_clk90 : std_logic := '0';

    component MMCME2_BASE
        generic (
            BANDWIDTH          : string  := "OPTIMIZED";
            CLKFBOUT_MULT_F    : real    := 5.0;
            CLKFBOUT_PHASE     : real    := 0.0;
            CLKIN1_PERIOD      : real    := 0.0;
            CLKOUT0_DIVIDE_F   : real    := 1.0;
            CLKOUT0_DUTY_CYCLE : real    := 0.5;
            CLKOUT0_PHASE      : real    := 0.0;
            CLKOUT1_DIVIDE     : integer := 1;
            CLKOUT1_DUTY_CYCLE : real    := 0.5;
            CLKOUT1_PHASE      : real    := 0.0;
            CLKOUT2_DIVIDE     : integer := 1;
            CLKOUT3_DIVIDE     : integer := 1;
            CLKOUT4_DIVIDE     : integer := 1;
            CLKOUT5_DIVIDE     : integer := 1;
            CLKOUT6_DIVIDE     : integer := 1;
            DIVCLK_DIVIDE      : integer := 1;
            REF_JITTER1        : real    := 0.0;
            STARTUP_WAIT       : boolean := false
        );
        port (
            CLKOUT0, CLKOUT0B, CLKOUT1, CLKOUT1B, CLKOUT2, CLKOUT2B,
            CLKOUT3, CLKOUT3B, CLKOUT4, CLKOUT5, CLKOUT6 : out std_logic;
            CLKFBOUT, CLKFBOUTB : out std_logic;
            LOCKED   : out std_logic;
            CLKIN1   : in  std_logic;
            PWRDWN   : in  std_logic;
            RST      : in  std_logic;
            CLKFBIN  : in  std_logic
        );
    end component;

    component BUFG
        port (O : out std_logic; I : in std_logic);
    end component;
begin
    gen_sim : if G_SIM generate
        sim_clk   <= not sim_clk after 2 ns;
        sim_clk90 <= transport sim_clk after 1 ns;
        clk_fast  <= sim_clk;
        clk_f90   <= sim_clk90;
        locked    <= '1';
    end generate;

    gen_syn : if not G_SIM generate
        u_mmcm : MMCME2_BASE
            generic map (
                CLKIN1_PERIOD => 10.0, CLKFBOUT_MULT_F => 10.0, DIVCLK_DIVIDE => 1,   -- VCO 1000 MHz
                CLKOUT0_DIVIDE_F => 4.0, CLKOUT0_PHASE => 0.0,
                CLKOUT1_DIVIDE => 4, CLKOUT1_PHASE => 90.0)
            port map (
                CLKIN1 => clk_in, CLKFBIN => fb_b, CLKFBOUT => fb, CLKFBOUTB => open,
                CLKOUT0 => c0, CLKOUT0B => open, CLKOUT1 => c1, CLKOUT1B => open,
                CLKOUT2 => open, CLKOUT2B => open, CLKOUT3 => open, CLKOUT3B => open,
                CLKOUT4 => open, CLKOUT5 => open, CLKOUT6 => open,
                LOCKED => locked, PWRDWN => '0', RST => '0');
        u_bfb : BUFG port map (O => fb_b, I => fb);
        u_b0  : BUFG port map (O => clk_fast, I => c0);
        u_b1  : BUFG port map (O => clk_f90, I => c1);
    end generate;
end architecture rtl;
