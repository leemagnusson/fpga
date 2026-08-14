library ieee;
use ieee.std_logic_1164.all;
use ieee.std_logic_arith.all;
use ieee.std_logic_unsigned.all;
library std;

entity top is
port
(
    clk : in std_logic;
    led : out std_logic_vector( 3 downto 0 )
);
end top;

architecture rtl of top is

    signal clk_100m_loc     : std_logic;
    signal clk_100m_tree    : std_logic;
    signal d_flop_sr        : std_logic_vector( 3 downto 0 ) := "0001";
    signal pulse_1hz        : std_logic := '0';
    signal hz_counter       : integer := 0;

begin

    clk_100m_loc <= clk;
    clk_100m_tree <= clk_100m_loc;

    process (pulse_1hz) is
    begin
        if rising_edge(pulse_1hz) then
            d_flop_sr <= d_flop_sr(2 downto 0) & d_flop_sr(3);
        end if;
    end process;

    led <= d_flop_sr( 3 downto 0 );

    process (clk_100m_tree) is
    begin
        if rising_edge(clk_100m_tree) then
            if hz_counter = 100_000_000 - 1 then
                hz_counter <= 0;
                pulse_1hz <= '1';
            else
                hz_counter <= hz_counter + 1;
                pulse_1hz <= '0';
            end if;
        end if;
    end process;
end rtl;
