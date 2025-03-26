library ieee;
use ieee.std_logic_1164.all;
use work.can_message_type.all;

entity can_sim is
end can_sim;

architecture testbench of can_sim is
    component can_timing is
        port (can_bus : inout can_message;
              clk : in std_logic);
    end component;
    signal clk : std_logic := '1';
    signal can_bus : can_message;
begin
    d1: can_timing
        port map(
            can_bus => can_bus,
            clk => clk
        );
    clk <= not clk after 33.3 ns;
end testbench;
