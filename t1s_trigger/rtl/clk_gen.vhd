-- 250 MHz sampling clocks (0 and 90 degrees) and a phase-aligned 125 MHz
-- processing clock from the board's 100 MHz.
-- Synthesis: MMCME2_BASE, VCO 1000 MHz, outputs divided by 4, 4 (90 deg) and 8, plus BUFGs.
-- Simulation (G_SIM): free-running clocks, no vendor library needed.
library ieee;
use ieee.std_logic_1164.all;
library unisim;
use unisim.vcomponents.all;   -- real primitives in Vivado, ci/unisim_stub.vhd elsewhere

entity clk_gen is
    generic (
        G_SIM : boolean := false
    );
    port (
        clk_in   : in  std_logic;          -- 100 MHz
        clk_fast : out std_logic;          -- 250 MHz
        clk_f90  : out std_logic;          -- 250 MHz, +90 degrees
        clk_div  : out std_logic;          -- 125 MHz, edges aligned with clk_fast
        locked   : out std_logic
    );
end entity clk_gen;

architecture rtl of clk_gen is
    signal fb, fb_b, c0, c1, c2 : std_logic;
    signal sim_clk, sim_clk90, sim_div : std_logic := '0';

begin
    gen_sim : if G_SIM generate
        sim_clk   <= not sim_clk after 2 ns;
        sim_clk90 <= transport sim_clk after 1 ns;
        process (sim_clk) begin if rising_edge(sim_clk) then sim_div <= not sim_div; end if; end process;
        clk_fast  <= sim_clk;
        clk_f90   <= sim_clk90;
        clk_div   <= sim_div;
        locked    <= '1';
    end generate;

    gen_syn : if not G_SIM generate
        u_mmcm : MMCME2_BASE
            generic map (
                CLKIN1_PERIOD => 10.0, CLKFBOUT_MULT_F => 10.0, DIVCLK_DIVIDE => 1,   -- VCO 1000 MHz
                CLKOUT0_DIVIDE_F => 4.0, CLKOUT0_PHASE => 0.0,
                CLKOUT1_DIVIDE => 4, CLKOUT1_PHASE => 90.0,
                CLKOUT2_DIVIDE => 8)
            port map (
                CLKIN1 => clk_in, CLKFBIN => fb_b, CLKFBOUT => fb, CLKFBOUTB => open,
                CLKOUT0 => c0, CLKOUT0B => open, CLKOUT1 => c1, CLKOUT1B => open,
                CLKOUT2 => c2, CLKOUT2B => open, CLKOUT3 => open, CLKOUT3B => open,
                CLKOUT4 => open, CLKOUT5 => open, CLKOUT6 => open,
                LOCKED => locked, PWRDWN => '0', RST => '0');
        u_bfb : BUFG port map (O => fb_b, I => fb);
        u_b0  : BUFG port map (O => clk_fast, I => c0);
        u_b1  : BUFG port map (O => clk_f90, I => c1);
        u_b2  : BUFG port map (O => clk_div, I => c2);
    end generate;
end architecture rtl;
