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
