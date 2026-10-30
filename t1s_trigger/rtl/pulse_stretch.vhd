-- Holds the output high for LEN clocks after the last input pulse.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity pulse_stretch is
    generic (
        LEN : positive := 10
    );
    port (
        clk   : in  std_logic;
        pulse : in  std_logic;
        q     : out std_logic
    );
end entity pulse_stretch;

architecture rtl of pulse_stretch is
    signal cnt : natural range 0 to LEN := 0;
begin
    q <= '1' when cnt /= 0 else '0';
    process (clk)
    begin
        if rising_edge(clk) then
            if pulse = '1' then
                cnt <= LEN;
            elsif cnt /= 0 then
                cnt <= cnt - 1;
            end if;
        end if;
    end process;
end architecture rtl;
