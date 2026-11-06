-- Four samples per clock of one input pin, 1 ns apart at 250 MHz.
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

entity oversample_in is
    generic (
        G_SIM : boolean := false
    );
    port (
        clk    : in  std_logic;                     -- 250 MHz, 0 degrees
        clk90  : in  std_logic;                     -- 250 MHz, 90 degrees
        d      : in  std_logic;                     -- the pin
        o      : out std_logic;                     -- pass-through (asynchronous)
        q      : out std_logic_vector(3 downto 0)   -- q(0) earliest ... q(3) latest, at clk
    );
end entity oversample_in;

architecture rtl of oversample_in is
    signal q1, q2, q3, q4 : std_logic := '1';

    component ISERDESE2
        generic (
            DATA_RATE         : string  := "DDR";
            DATA_WIDTH        : integer := 4;
            INTERFACE_TYPE    : string  := "MEMORY";
            IOBDELAY          : string  := "NONE";
            NUM_CE            : integer := 2;
            OFB_USED          : string  := "FALSE";
            SERDES_MODE       : string  := "MASTER";
            IS_CLKB_INVERTED  : bit     := '0';
            IS_OCLKB_INVERTED : bit     := '0'
        );
        port (
            O            : out std_logic;
            Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8 : out std_logic;
            SHIFTOUT1, SHIFTOUT2 : out std_logic;
            BITSLIP      : in  std_logic;
            CE1, CE2     : in  std_logic;
            CLK, CLKB    : in  std_logic;
            CLKDIV, CLKDIVP : in std_logic;
            D, DDLY      : in  std_logic;
            DYNCLKDIVSEL, DYNCLKSEL : in std_logic;
            OCLK, OCLKB  : in  std_logic;
            OFB          : in  std_logic;
            RST          : in  std_logic;
            SHIFTIN1, SHIFTIN2 : in std_logic
        );
    end component;
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

    -- present the four samples of the period that just ended, in time order
    process (clk)
    begin
        if rising_edge(clk) then
            q <= q4 & q3 & q2 & q1;
        end if;
    end process;
end architecture rtl;
