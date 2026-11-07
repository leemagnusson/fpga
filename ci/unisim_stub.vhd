-- Minimal behavioural stand-ins for the Xilinx UNISIM primitives instantiated
-- in this repo, so the open-source CI flow (GHDL + Yosys) can build designs
-- that use them. Vivado ignores this file and uses the real UNISIM library.
--
-- Compiled into library "unisim" by ci/check.sh.

library ieee;
use ieee.std_logic_1164.all;

package vcomponents is
    component IBUF is
        port ( I : in std_logic; O : out std_logic );
    end component;
    component OBUF is
        port ( I : in std_logic; O : out std_logic );
    end component;
    component BUFG is
        port ( I : in std_logic; O : out std_logic );
    end component;
    component FDRE is
        generic ( INIT : bit := '0' );
        port ( Q : out std_logic; C, CE, D, R : in std_logic );
    end component;
    component FDSE is
        generic ( INIT : bit := '1' );
        port ( Q : out std_logic; C, CE, D, S : in std_logic );
    end component;
    component ISERDESE2 is
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
            O : out std_logic;
            Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8 : out std_logic;
            SHIFTOUT1, SHIFTOUT2 : out std_logic;
            BITSLIP, CE1, CE2, CLK, CLKB, CLKDIV, CLKDIVP, D, DDLY,
            DYNCLKDIVSEL, DYNCLKSEL, OCLK, OCLKB, OFB, RST, SHIFTIN1, SHIFTIN2 : in std_logic
        );
    end component;
    component MMCME2_BASE is
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
            LOCKED  : out std_logic;
            CLKIN1, PWRDWN, RST, CLKFBIN : in std_logic
        );
    end component;
end package vcomponents;

library ieee;
use ieee.std_logic_1164.all;

entity IBUF is
    port ( I : in std_logic; O : out std_logic );
end IBUF;
architecture rtl of IBUF is
begin
    O <= I;
end rtl;

library ieee;
use ieee.std_logic_1164.all;

entity OBUF is
    port ( I : in std_logic; O : out std_logic );
end OBUF;
architecture rtl of OBUF is
begin
    O <= I;
end rtl;

library ieee;
use ieee.std_logic_1164.all;

entity BUFG is
    port ( I : in std_logic; O : out std_logic );
end BUFG;
architecture rtl of BUFG is
begin
    O <= I;
end rtl;

-- D flip-flop, clock enable, synchronous reset
library ieee;
use ieee.std_logic_1164.all;

entity FDRE is
    generic ( INIT : bit := '0' );
    port
    (
        Q  : out std_logic;
        C  : in  std_logic;
        CE : in  std_logic;
        D  : in  std_logic;
        R  : in  std_logic
    );
end FDRE;
architecture rtl of FDRE is
    signal q_i : std_logic := to_stdulogic(INIT);
begin
    process (C) is
    begin
        if rising_edge(C) then
            if R = '1' then
                q_i <= '0';
            elsif CE = '1' then
                q_i <= D;
            end if;
        end if;
    end process;
    Q <= q_i;
end rtl;

-- D flip-flop, clock enable, synchronous set
library ieee;
use ieee.std_logic_1164.all;

entity FDSE is
    generic ( INIT : bit := '1' );
    port
    (
        Q  : out std_logic;
        C  : in  std_logic;
        CE : in  std_logic;
        D  : in  std_logic;
        S  : in  std_logic
    );
end FDSE;
architecture rtl of FDSE is
    signal q_i : std_logic := to_stdulogic(INIT);
begin
    process (C) is
    begin
        if rising_edge(C) then
            if S = '1' then
                q_i <= '1';
            elsif CE = '1' then
                q_i <= D;
            end if;
        end if;
    end process;
    Q <= q_i;
end rtl;

-- Oversampling input deserialiser: enough for a build check (D registered on
-- CLK to all four outputs; the real one samples at four clock phases).
library ieee;
use ieee.std_logic_1164.all;

entity ISERDESE2 is
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
        O : out std_logic;
        Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8 : out std_logic;
        SHIFTOUT1, SHIFTOUT2 : out std_logic;
        BITSLIP, CE1, CE2, CLK, CLKB, CLKDIV, CLKDIVP, D, DDLY,
        DYNCLKDIVSEL, DYNCLKSEL, OCLK, OCLKB, OFB, RST, SHIFTIN1, SHIFTIN2 : in std_logic
    );
end ISERDESE2;
architecture rtl of ISERDESE2 is
    signal q : std_logic := '1';
begin
    O <= D;
    process (CLK) begin if rising_edge(CLK) then q <= D; end if; end process;
    Q1 <= q; Q2 <= q; Q3 <= q; Q4 <= q;
    Q5 <= '0'; Q6 <= '0'; Q7 <= '0'; Q8 <= '0';
    SHIFTOUT1 <= '0'; SHIFTOUT2 <= '0';
end rtl;

-- Clock manager: passes the input clock through (the real one multiplies and
-- phase-shifts it); enough for a build check.
library ieee;
use ieee.std_logic_1164.all;

entity MMCME2_BASE is
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
        LOCKED  : out std_logic;
        CLKIN1, PWRDWN, RST, CLKFBIN : in std_logic
    );
end MMCME2_BASE;
architecture rtl of MMCME2_BASE is
begin
    CLKOUT0 <= CLKIN1; CLKOUT0B <= not CLKIN1;
    CLKOUT1 <= CLKIN1; CLKOUT1B <= not CLKIN1;
    CLKOUT2 <= CLKIN1; CLKOUT2B <= not CLKIN1;
    CLKOUT3 <= CLKIN1; CLKOUT3B <= not CLKIN1;
    CLKOUT4 <= CLKIN1; CLKOUT5 <= CLKIN1; CLKOUT6 <= CLKIN1;
    CLKFBOUT <= CLKIN1; CLKFBOUTB <= not CLKIN1;
    LOCKED <= '1';
end rtl;
