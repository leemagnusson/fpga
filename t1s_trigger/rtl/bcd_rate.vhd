-- Events per tick, counted directly in BCD so the display needs no binary to
-- decimal conversion. Counts pulses between ticks (one tick per second in
-- top), latches the total on the tick and starts again. Saturates at
-- 10**DIGITS - 1.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity bcd_rate is
    generic (
        DIGITS : positive := 5
    );
    port (
        clk   : in  std_logic;
        pulse : in  std_logic;
        tick  : in  std_logic;
        bcd   : out std_logic_vector(4 * DIGITS - 1 downto 0)   -- digit 0 = least significant, nibble 0
    );
end entity bcd_rate;

architecture rtl of bcd_rate is
    signal acc     : std_logic_vector(4 * DIGITS - 1 downto 0) := (others => '0');
    signal latched : std_logic_vector(4 * DIGITS - 1 downto 0) := (others => '0');
    signal full    : std_logic := '0';
begin
    bcd <= latched;

    process (clk)
        variable carry : boolean;
        variable d     : unsigned(3 downto 0);
    begin
        if rising_edge(clk) then
            if tick = '1' then
                latched <= acc;
                acc     <= (others => '0');
                full    <= '0';
            elsif pulse = '1' and full = '0' then
                carry := true;
                for i in 0 to DIGITS - 1 loop
                    d := unsigned(acc(4 * i + 3 downto 4 * i));
                    if carry then
                        if d = 9 then
                            acc(4 * i + 3 downto 4 * i) <= x"0";
                        else
                            acc(4 * i + 3 downto 4 * i) <= std_logic_vector(d + 1);
                            carry := false;
                        end if;
                    end if;
                end loop;
                if carry then                       -- overflow: stick at 99..9
                    for i in 0 to DIGITS - 1 loop
                        acc(4 * i + 3 downto 4 * i) <= x"9";
                    end loop;
                    full <= '1';
                end if;
            end if;
        end if;
    end process;
end architecture rtl;
