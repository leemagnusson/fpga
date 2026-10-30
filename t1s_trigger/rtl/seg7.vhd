-- Four-digit multiplexed seven-segment display (Basys 3: common anode,
-- anodes and segments active low). Shows a 16-bit value in hex; dp lights
-- the decimal point of the selected digits.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity seg7 is
    port (
        clk   : in  std_logic;
        value : in  std_logic_vector(15 downto 0);
        dp    : in  std_logic_vector(3 downto 0);  -- '1' = point on, bit 0 = rightmost digit
        seg   : out std_logic_vector(6 downto 0);  -- a..g, active low
        dp_o  : out std_logic;                     -- active low
        an    : out std_logic_vector(3 downto 0)   -- active low
    );
end entity seg7;

architecture rtl of seg7 is
    signal refresh : unsigned(17 downto 0) := (others => '0');
    signal nib     : std_logic_vector(3 downto 0);
    signal digit   : integer range 0 to 3;
begin
    process (clk)
    begin
        if rising_edge(clk) then
            refresh <= refresh + 1;
        end if;
    end process;

    digit <= to_integer(refresh(17 downto 16));
    with digit select nib <=
        value(3 downto 0)   when 0,
        value(7 downto 4)   when 1,
        value(11 downto 8)  when 2,
        value(15 downto 12) when others;

    an   <= "1110" when digit = 0 else
            "1101" when digit = 1 else
            "1011" when digit = 2 else
            "0111";
    dp_o <= not dp(digit);

    with nib select seg <=
        "1000000" when x"0",
        "1111001" when x"1",
        "0100100" when x"2",
        "0110000" when x"3",
        "0011001" when x"4",
        "0010010" when x"5",
        "0000010" when x"6",
        "1111000" when x"7",
        "0000000" when x"8",
        "0010000" when x"9",
        "0001000" when x"A",
        "0000011" when x"B",
        "1000110" when x"C",
        "0100001" when x"D",
        "0000110" when x"E",
        "0001110" when others;
end architecture rtl;
