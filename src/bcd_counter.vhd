library ieee;
use ieee.std_logic_1164.all;

entity bcd_counter is
    Port ( clk : in std_logic;
           reset : in std_logic;
           pulse_in : in std_logic;
           carry_out : out std_logic;
           bcd_out : out std_logic_vector (3 downto 0));
end bcd_counter;

architecture Behavioral of bcd_counter is
    signal count : std_logic_vector (3 downto 0) := "0000";
begin
    process(clk, reset)
    begin
        carry_out <= '0';
        if reset = '1' then
            count <= "0000";
        elsif rising_edge(clk) then
            if pulse_in = '1' then
                if count = "1001" then
                    count <= "0000";
                    carry_out <= '1';
                else
                    count <= count + 1;
                end if;
            end if;
        end if;
    end process;

    bcd_out <= count;
end Behavioral;