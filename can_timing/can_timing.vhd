library ieee;

package can_message_type is
type can_message is (IDLE, SOF, OUT1, OUT2, OUT3, OUT4, OUT5, OUT6, IN1, IN2, IN3, IN4, IN5, IN6);
end package can_message_type;

library ieee;
use ieee.std_logic_1164.all;
use work.can_message_type.all;

entity can_timing is
  port (
    can_bus: inout can_message;
    clk: in std_logic
  ) ;
end can_timing;

architecture arch of can_timing is
    signal can_msg : can_message := IDLE;
    signal counter : integer range 0 to 15000 := 0;
    constant OVERHEAD : integer := 33*10;
    constant SOF_LEN : integer := OVERHEAD + 8*10; -- add some bitstuff time
    constant OUT_LEN : integer := OVERHEAD + 48*10;
    constant IN_LEN : integer :=  OVERHEAD + 48*10;
    constant RESPONSE_DELAY : integer := 7500;

begin
    process (clk) is
    begin
        if rising_edge(clk) then
            counter <= counter + 1;
            if counter = 15000 then
                counter <= 0;
            end if;
        end if;
    end process;
    
    process (counter) is
    begin
        if counter = 0 then
            can_msg <= SOF;
        elsif counter = SOF_LEN then
            can_msg <= OUT1;
        elsif counter = SOF_LEN+OUT_LEN then
            can_msg <= OUT2;
        elsif counter = SOF_LEN+2*OUT_LEN then
            can_msg <= OUT3;
        elsif counter = SOF_LEN+3*OUT_LEN then
            can_msg <= OUT4;
        elsif counter = SOF_LEN+4*OUT_LEN then
            can_msg <= OUT5;
        elsif counter = SOF_LEN+5*OUT_LEN then
            can_msg <= OUT6;
        elsif counter = SOF_LEN+6*OUT_LEN then
            can_msg <= IDLE;
        elsif counter = RESPONSE_DELAY then
            can_msg <= IN1;
        elsif counter = RESPONSE_DELAY+IN_LEN then
            can_msg <= IN2;
        elsif counter = RESPONSE_DELAY+2*IN_LEN then
            can_msg <= IN3;
        elsif counter = RESPONSE_DELAY+3*IN_LEN then
            can_msg <= IN4;
        elsif counter = RESPONSE_DELAY+4*IN_LEN then
            can_msg <= IN5;
        elsif counter = RESPONSE_DELAY+5*IN_LEN then
            can_msg <= IN6;
        elsif counter = RESPONSE_DELAY+6*IN_LEN then
            can_msg <= IDLE;
        end if;
    end process;

    can_bus <= can_msg;
end arch;
