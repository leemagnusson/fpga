library ieee;
use ieee.std_logic_1164.all;

entity bcd_count4 is
    Port ( clk : in std_logic;
           reset : in std_logic;
           pulse_in : in std_logic;
           carry_out : out std_logic;
           bcd_out : out array (0 to 3) of std_logic_vector (3 downto 0));
end bcd_count4;

architecture structural of bcd_count4 is
    component bcd_counter is
        Port ( clk : in std_logic;
            reset : in std_logic;
            pulse_in : in std_logic;
            carry_out : out std_logic;
            bcd_out : out std_logic_vector (3 downto 0));
    end bcd_counter;
    signal c1, c2, c3 : std_logic;
begin
    d1: bcd_counter
        port map(
            pulse_in => pulse_in,
            clk => clk,
            reset => reset,
            bcd_out => bcd_out(0),
            carry_out => c1
        );
    d2: bcd_counter
        port map (
            pulse_in => c1,
            clk => clk,
            reset => reset,
            bcd_out => bcd_out(1),
            carry_out => c2
        );
    d3: bcd_counter
        port map (
            pulse_in => c2,
            clk => clk,
            reset => reset,
            bcd_out => bcd_out(2),
            carry_out => c3
        );
    d4: bcd_counter
        port map (
            pulse_in => c3,
            clk => clk,
            reset => reset,
            bcd_out => bcd_out(3),
            carry_out => carry_out
        );
    
end structural;