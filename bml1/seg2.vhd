library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity top is
  port (
    clk : in std_logic;
    button_l, button_r, button_u, button_d, button_c : in std_logic;
    digit : out std_logic_vector(3 downto 0);
    seg_a, seg_b, seg_c, seg_d, seg_e, seg_f, seg_g, seg_p : out std_logic;
    led : out std_logic_vector(15 downto 0);
    switch : in std_logic_vector(15 downto 0)
  ) ;
end top;

architecture arch of top is
    signal segs : std_logic_vector(6 downto 0);
    signal number : integer := 5;
    signal current_digit : integer := 0;
    signal clk_1hz : std_logic := '0';
    signal clk_1khz : std_logic := '0';
    signal counter_1hz : integer := 0;
    signal counter_1khz : integer := 0;
    signal digit_sel : integer := 0;
    type digit_array_type is array(0 to 3) of std_logic_vector(3 downto 0);
    signal digit_array : digit_array_type := ("0000", "0000", "0000", "0000");
    signal reset : std_logic := '0';
    signal led_val : std_logic_vector(15 downto 0) := "0000000000000001";
    signal button_l_pressed : std_logic := '0';
    signal last_button_l : std_logic := '0';
    signal last_button_r : std_logic := '0';
    signal button_r_pressed : std_logic := '0';
    signal button_l2 : std_logic := '0';
    signal button_r2 : std_logic := '0';
    signal button_l_count : integer := 0;
    signal clk_1hz_pulse : std_logic := '0';
    signal button_count : integer := 0;
    signal last_button_count : integer := 0;
begin
    -- process (clk_1hz) is
    -- begin
    --     if rising_edge(clk_1hz) then
    --         if number = 9999 then
    --             number <= 0;
    --         else
    --             number <= number + 1;
    --         end if;
    --     end if;
    -- end process;

    process (button_c) is
    begin
        if button_c = '1' then
            reset <= '1';
        else
            reset <= '0';
        end if;
    end process;

    -- process (clk, reset) is
    -- begin
    --     if reset = '1' then
    --         digit_array <= ("0000", "0000", "0000", "0000");
    --     else
    --         if rising_edge(clk) then
    --             if (clk_1hz_pulse = '1' or button_l_pressed = '1') then
    --                 if digit_array(0) = "1001" then
    --                     digit_array(0) <= "0000";
    --                     if digit_array(1) = "1001" then
    --                         digit_array(1) <= "0000";
    --                         if digit_array(2) = "1001" then
    --                             digit_array(2) <= "0000";
    --                             if digit_array(3) = "1001" then
    --                                 digit_array(3) <= "0000";
    --                             else
    --                                 digit_array(3) <= std_logic_vector(unsigned(digit_array(3)) + 1);
    --                             end if;
    --                         else
    --                             digit_array(2) <= std_logic_vector(unsigned(digit_array(2)) + 1);
    --                         end if;
    --                     else
    --                         digit_array(1) <= std_logic_vector(unsigned(digit_array(1)) + 1);
    --                     end if;
    --                 else
    --                     digit_array(0) <= std_logic_vector(unsigned(digit_array(0)) + 1);
    --                 end if;
    --             end if;
    --         end if;
    --     end if;
    -- end process;

    digit_array(0) <= std_logic_vector(to_unsigned(last_button_count*3, 4));
        


    process (clk) is
    begin
        if rising_edge(clk) then
            if counter_1hz = 50000000 then
                counter_1hz <= 0;
                clk_1hz <= not clk_1hz;
                if (clk_1hz = '0') then
                    clk_1hz_pulse <= '1';
                end if;
            else
                counter_1hz <= counter_1hz + 1;
                clk_1hz_pulse <= '0';
            end if;
        end if;
    end process;

    process (clk) is
    begin
        if rising_edge(clk) then
            if clk_1hz_pulse = '1' then
                button_count <= 0;
                last_button_count <= button_count;
            elsif button_l_pressed = '1' then
                button_count <= button_count + 1;
            end if;
        end if;
    end process;

    process (clk) is
    begin
        if rising_edge(clk) then
            if counter_1khz = 50000 then
                counter_1khz <= 0;
                clk_1khz <= not clk_1khz;
            else
                counter_1khz <= counter_1khz + 1;
            end if;
        end if;
    end process;

    process (clk_1khz) is
    begin
        if rising_edge(clk_1khz) then
            if digit_sel = 3 then
                digit_sel <= 0;
            else
                digit_sel <= digit_sel + 1;
            end if;
        end if;
    end process;

    process (digit_sel, digit_array) is
    begin
        case digit_sel is
            when 0 =>
                current_digit <= to_integer(unsigned(digit_array(0)));
            when 1 =>
                current_digit <= to_integer(unsigned(digit_array(1)));
            when 2 =>
                current_digit <= to_integer(unsigned(digit_array(2)));
            when 3 =>
                current_digit <= to_integer(unsigned(digit_array(3)));
            when others =>
                current_digit <= 0;
        end case;
    end process;

    process (button_l, clk) is
    begin
        if rising_edge(clk) then
            button_l2 <= button_l;
            if button_l2 = '1' and last_button_l = '0' and button_l_count = 10000000 then
                button_l_pressed <= '1';
                button_l_count <= 0;
            else
                button_l_pressed <= '0';
                if button_l_count < 10000000 then
                    button_l_count <= button_l_count + 1;
                end if;
            end if;
            last_button_l <= button_l2;
        end if;
    end process;

    -- process (button_r, clk) is
    -- begin
    --     if rising_edge(clk) then
    --         button_r_pressed <= button_r;
    --     end if;
    -- end process;

    process (reset, clk) is
    begin
        if reset = '1' then
            led_val <= "0000000000000001";
        else
            if rising_edge(clk) then
                -- button_l2 <= button_l;
                button_r2 <= button_r;

                -- if button_l2 = '1' and last_button_l = '0' then
                --     button_l_pressed <= '1';
                --     --led_val <= led_val(14 downto 0) & led_val(15);
                -- else
                --     button_l_pressed <= '0';
                -- end if;
                -- last_button_l <= button_l2;

                if button_r2 = '1' and last_button_r = '0' then
                    button_r_pressed <= '1';
                    --led_val <= led_val(0) & led_val(15 downto 1);
                else
                    button_r_pressed <= '0';
                end if;
                last_button_r <= button_r2;

                if button_r_pressed = '1' then
                    led_val <= led_val(0) & led_val(15 downto 1);
                end if;

                if button_l_pressed = '1' then
                    led_val <= led_val(14 downto 0) & led_val(15);
                end if;

                -- if button_l_pressed = '1' then
                    
                -- -- elsif rising_edge(button_l_pressed) then
                -- --     led_val <= led_val(0) & led_val(15 downto 1);
                -- end if;
            end if;
        end if;
    end process;

    -- process (digit_sel, number) is
    -- begin
    --     case digit_sel is
    --         when 0 =>
    --             current_digit <= number mod 10;
    --         when 1 =>
    --             current_digit <= (number / 10) mod 10;
    --         when 2 =>
    --             current_digit <= (number / 100) mod 10;
    --         when 3 =>
    --             current_digit <= (number / 1000) mod 10;
    --         when others =>
    --             current_digit <= 0;
    --     end case;
    -- end process;

    with digit_sel select
        digit <= "1110" when 0,
                 "1101" when 1,
                 "1011" when 2,
                 "0111" when 3,
                 "1111" when others;

    with current_digit select
        segs <= "0000001" when 0,
                "1001111" when 1,
                "0010010" when 2,
                "0000110" when 3,
                "1001100" when 4,
                "0100100" when 5,
                "0100000" when 6,
                "0001111" when 7,
                "0000000" when 8,
                "0000100" when 9,
                "1111111" when others;

    seg_a <= segs(6);
    seg_b <= segs(5);
    seg_c <= segs(4);
    seg_d <= segs(3);
    seg_e <= segs(2);
    seg_f <= segs(1);
    seg_g <= segs(0);
    seg_p <= '1';

    led <= led_val;
    --led <= switch;

end arch ; -- arch