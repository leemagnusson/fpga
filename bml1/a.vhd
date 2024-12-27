library ieee
use ieee.std_logic_1164.all

entity ent is
  port (
    a,b,c,d : in std_logic;
    q : out std_logic
  ) ;
end ent;

architecture arch of ent is

    signal abcd : std_vector (3 downto 0);

begin
    q <= ((not a) and b) or a or (a and (not b));
    q <= ((not a) and C and (not d)) or ((not b) and c) or (b and c and (not (d)));
    q <= ((not a) or b) and ((not b) or c or (not d)) and ((not a) and d); or d
    q <= not ((not a) and (not b) and ((c and (not d)) or (c and d)));
    q <= not ((a and (not b) and c) or ((not a) and (not b) and c) or (a and (not b) and (not c)) or ((not a) and b and c));
    q <= (not a) and (not b) and (((not c) and d) or (c and (not d))); 

    q <= '1' when (not a) and c and (not d) else
         '1' when (not b) and c else
         '1' when b and c and (not d) else
         '0';

    abcd <= a & b & c & d;
    with adcd select
        q <=    '1' when "0010"|"0110",
                '1' when "0010"|"1010"|"0011"|"1011",
                '1' when "0110"|"1110",
                '0' when others;


    q <= '0' when abcd = "0010" or abcd = "0011" else
         '1';
          
    with abcd select
        q <=    '0' when "0010"|"0011",
                '1' when others;

    with abcd select
        q <=    '1' when "0001"|"0010",
                '0' when others;



end arch ; -- arch
