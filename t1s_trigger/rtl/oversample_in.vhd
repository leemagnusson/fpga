-- Eight samples per 125 MHz clock of one input pin, 1 ns apart: four per
-- 250 MHz period from an oversampling ISERDES, two periods gathered per
-- clk_div cycle so the arithmetic downstream runs at 125 MHz.
--
-- Synthesis: an ISERDESE2 in OVERSAMPLE mode, which samples D on the rising
-- and falling edges of CLK and of OCLK (CLK shifted by 90 degrees), i.e. at
-- 0, 90, 180 and 270 degrees of each clock period. The four results are
-- re-registered on the rising edge of CLK so that q(0..3) are consecutive in
-- time; q(0) is the sample taken at the previous rising edge (the ISERDES
-- updates Q1 at the same instant we read it, so the old value is captured).
-- The pass-through output o is the plain input for the 100 MHz decoder.
--
-- Simulation (G_SIM): the same thing done with four flip-flops, so the
-- testbench needs no vendor library.
library ieee;
use ieee.std_logic_1164.all;
library unisim;
use unisim.vcomponents.all;   -- real primitives in Vivado, ci/unisim_stub.vhd elsewhere

entity oversample_in is
    generic (
        G_SIM : boolean := false
    );
    port (
        clk    : in  std_logic;                     -- 250 MHz, 0 degrees
        clk90  : in  std_logic;                     -- 250 MHz, 90 degrees
        clk_div : in std_logic;                     -- 125 MHz, aligned with clk
        d      : in  std_logic;                     -- the pin
        o      : out std_logic;                     -- pass-through (asynchronous)
        q      : out std_logic_vector(7 downto 0)   -- q(0) earliest ... q(7) latest, at clk_div
    );
end entity oversample_in;

architecture rtl of oversample_in is
    signal q1, q2, q3, q4 : std_logic := '1';
    signal pair : std_logic_vector(7 downto 0) := (others => '1');   -- last two 250 MHz periods

begin
    gen_sim : if G_SIM generate
        o <= d;
        process (clk)   begin if rising_edge(clk)   then q1 <= d; end if; end process;
        process (clk90) begin if rising_edge(clk90) then q2 <= d; end if; end process;
        process (clk)   begin if falling_edge(clk)  then q3 <= d; end if; end process;
        process (clk90) begin if falling_edge(clk90) then q4 <= d; end if; end process;
    end generate;

    gen_syn : if not G_SIM generate
        u_serdes : ISERDESE2
            generic map (
                DATA_RATE => "DDR", DATA_WIDTH => 4, INTERFACE_TYPE => "OVERSAMPLE",
                IOBDELAY => "NONE", NUM_CE => 1, OFB_USED => "FALSE", SERDES_MODE => "MASTER",
                IS_CLKB_INVERTED => '1', IS_OCLKB_INVERTED => '1')
            port map (
                O => o, Q1 => q1, Q2 => q2, Q3 => q3, Q4 => q4,
                Q5 => open, Q6 => open, Q7 => open, Q8 => open,
                SHIFTOUT1 => open, SHIFTOUT2 => open,
                BITSLIP => '0', CE1 => '1', CE2 => '1',
                CLK => clk, CLKB => clk, CLKDIV => '0', CLKDIVP => '0',
                D => d, DDLY => '0', DYNCLKDIVSEL => '0', DYNCLKSEL => '0',
                OCLK => clk90, OCLKB => clk90, OFB => '0', RST => '0',
                SHIFTIN1 => '0', SHIFTIN2 => '0');
    end generate;

    -- shift the four samples of the period that just ended into an 8-sample
    -- window; clk_div (every other clk edge) takes a complete window each time,
    -- whichever of the two phases it lands on
    process (clk)
    begin
        if rising_edge(clk) then
            pair <= q4 & q3 & q2 & q1 & pair(7 downto 4);
        end if;
    end process;
    process (clk_div)
    begin
        if rising_edge(clk_div) then
            q <= pair;
        end if;
    end process;
end architecture rtl;
