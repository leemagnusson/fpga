-- Testbench for the OLED status display (oled_status: rate counters, text
-- screen, SSD1331 driver). Feeds a known number of pulses into each rate
-- counter, ticks the second, then decodes the SPI stream like the panel
-- would: checks the power-up sequence byte for byte, the window commands,
-- that every pixel byte goes out with D/C high, and dumps the first frame
-- after the tick to a PPM image (see sim/ppm2png.py) with a few pixels
-- checked against the layout. Prints "TB PASSED".
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;
use work.trig_screen_pkg.all;

entity tb_oled is
    generic (
        PPM_FILE : string := "oled_frame.ppm"
    );
end entity tb_oled;

architecture sim of tb_oled is
    constant SPI_DIV : positive := 4;
    constant CLKS_PER_MS : positive := 100;     -- a "millisecond" is 1 us here

    signal clk      : std_logic := '0';
    signal done     : boolean := false;
    signal sec_tick : std_logic := '0';
    signal events   : std_logic_vector(N_RATES - 1 downto 0) := (others => '0');
    signal sw       : std_logic_vector(15 downto 0);
    signal frame    : std_logic;
    signal cs_n, mosi, sck, dc, res_n, vccen, pmoden : std_logic;

    -- pulses per channel: exercises leading-zero blanking, 0, saturation (100000 -> 99999)
    type t_counts is array (0 to N_RATES - 1) of natural;
    constant COUNTS : t_counts := (12345, 7, 100000, 0, 64, 1, 2, 3, 4, 5, 60, 99999, 8, 9);
    signal pulses_done : std_logic_vector(N_RATES - 1 downto 0) := (others => '0');
    signal tick_seen   : boolean := false;

    type t_bytes is array (natural range <>) of std_logic_vector(7 downto 0);
    constant INIT : t_bytes := (
        x"FD", x"12", x"AE", x"A0", x"72", x"A1", x"00", x"A2", x"00", x"A4", x"A8", x"3F",
        x"AD", x"8E", x"B0", x"0B", x"B1", x"31", x"B3", x"F0", x"8A", x"64", x"8B", x"78",
        x"8C", x"64", x"BB", x"3A", x"BE", x"3E", x"87", x"06", x"81", x"91", x"82", x"50",
        x"83", x"7D", x"2E", x"25", x"00", x"00", x"5F", x"3F");
    constant WINDOW : t_bytes := (x"15", x"00", x"5F", x"75", x"00", x"3F");

    type t_image is array (0 to 63, 0 to 95) of std_logic_vector(15 downto 0);
    signal errors : natural := 0;

    constant C_YELLOW : std_logic_vector(15 downto 0) := x"FFE0";
    constant C_GREY   : std_logic_vector(15 downto 0) := x"4208";
    constant C_WHITE  : std_logic_vector(15 downto 0) := x"FFFF";
    constant C_CYAN   : std_logic_vector(15 downto 0) := x"07FF";
    constant C_GREEN  : std_logic_vector(15 downto 0) := x"07E0";
begin
    clk <= not clk after 5 ns when not done else '0';

    -- SW15..12 = 5 (node ID), SW11 on, SW10 off (100 ns), SW9..0 = 1010101011
    sw <= "0101" & '1' & '0' & "1010101011";

    dut : entity work.oled_status
        generic map (CLKS_PER_MS => CLKS_PER_MS, SPI_DIV => SPI_DIV)
        port map (clk => clk, sec_tick => sec_tick, sw => sw, plca_synced => '1',
                  events => events, frame => frame,
                  cs_n => cs_n, mosi => mosi, sck => sck, dc => dc,
                  res_n => res_n, vccen => vccen, pmoden => pmoden);

    -- pulse generators
    g_pulse : for i in 0 to N_RATES - 1 generate
        process
        begin
            wait until rising_edge(clk);
            wait for 1 us;
            for n in 1 to COUNTS(i) loop
                events(i) <= '1';
                wait until rising_edge(clk);
                events(i) <= '0';
                wait until rising_edge(clk);
            end loop;
            pulses_done(i) <= '1';
            wait;
        end process;
    end generate;

    -- the second tick, once every channel has delivered its pulses
    process
    begin
        wait until pulses_done = (pulses_done'range => '1');
        wait until rising_edge(clk);
        sec_tick <= '1';
        wait until rising_edge(clk);
        sec_tick <= '0';
        tick_seen <= true;
        wait;
    end process;

    -- power-up sequence sanity: reset pulse, VCCEN after the init list
    process
    begin
        wait until pmoden = '1';
        assert res_n = '1' report "RES should be high while PMODEN comes up" severity error;
        wait until res_n = '0';
        assert vccen = '0' report "VCCEN before reset" severity error;
        wait until res_n = '1';
        wait;
    end process;

    -- SPI decode: byte on every 8 rising sck edges while cs_n is low
    monitor : process
        variable sreg   : std_logic_vector(7 downto 0);
        variable nbits  : natural := 0;
        variable byte   : std_logic_vector(7 downto 0);
        variable dc_v   : std_logic;
        variable phase  : natural := 0;        -- 0 init list, 1 display on, 2 window, 3 pixels
        variable idx    : natural := 0;
        variable img    : t_image;
        variable hi     : std_logic_vector(7 downto 0);
        variable capturing : boolean := false;
        variable nframes : natural := 0;
        variable lit    : natural := 0;
        file f          : text;
        variable l      : line;

        procedure check_px(px, py : natural; exp : std_logic_vector(15 downto 0); what : string) is
        begin
            if img(py, px) /= exp then
                report "pixel (" & integer'image(px) & "," & integer'image(py) & ") " & what &
                       " wrong" severity error;
                errors <= errors + 1;
            end if;
        end procedure;

        procedure get_byte is
        begin
            nbits := 0;
            loop
                wait until rising_edge(sck);
                if cs_n = '1' then
                    report "SCK edge with CS high" severity error;
                    errors <= errors + 1;
                end if;
                sreg := sreg(6 downto 0) & mosi;
                nbits := nbits + 1;
                exit when nbits = 8;
            end loop;
            byte := sreg;
            dc_v := dc;
        end procedure;
    begin
        -- init list
        for i in INIT'range loop
            get_byte;
            if byte /= INIT(i) or dc_v /= '0' then
                report "init byte " & integer'image(i) & " wrong" severity error;
                errors <= errors + 1;
            end if;
        end loop;
        assert vccen = '0' report "VCCEN on before the init list finished" severity error;
        -- display on
        get_byte;
        assert byte = x"AF" and dc_v = '0' report "expected display on" severity error;
        assert vccen = '1' report "display on before VCCEN" severity error;

        -- frames
        loop
            for i in WINDOW'range loop
                get_byte;
                if byte /= WINDOW(i) or dc_v /= '0' then
                    report "window byte " & integer'image(i) & " wrong in frame " &
                           integer'image(nframes) severity error;
                    errors <= errors + 1;
                end if;
            end loop;
            capturing := tick_seen;
            for y in 0 to 63 loop
                for x in 0 to 95 loop
                    get_byte;
                    hi := byte;
                    if dc_v /= '1' then errors <= errors + 1; end if;
                    get_byte;
                    if dc_v /= '1' then errors <= errors + 1; end if;
                    img(y, x) := hi & byte;
                end loop;
            end loop;
            nframes := nframes + 1;
            exit when capturing;
        end loop;

        -- dump
        file_open(f, PPM_FILE, write_mode);
        write(l, string'("P3")); writeline(f, l);
        write(l, string'("96 64 255")); writeline(f, l);
        for y in 0 to 63 loop
            for x in 0 to 95 loop
                write(l, to_integer(unsigned(img(y, x)(15 downto 11))) * 255 / 31); write(l, ' ');
                write(l, to_integer(unsigned(img(y, x)(10 downto 5))) * 255 / 63); write(l, ' ');
                write(l, to_integer(unsigned(img(y, x)(4 downto 0))) * 255 / 31); write(l, ' ');
                if img(y, x) /= x"0000" then lit := lit + 1; end if;
            end loop;
            writeline(f, l);
        end loop;
        file_close(f);
        report "frames seen " & integer'image(nframes) & ", lit pixels " & integer'image(lit);

        -- layout checks (character cells are 6 x 8, glyphs 5 x 7)
        check_px(2, 0, C_YELLOW, "header '1' top");                 -- "100NS": '1' row 0 = 00100
        check_px(0, 1, x"0000", "header '1' left of stem");
        check_px(66 + 1, 0, C_GREEN, "PLCA green");                -- 'P' at col 11, row 0 = 1111.
        check_px(1, 8, C_WHITE, "BCN on, white");                  -- 'B' col 0 row 1: 1111.
        check_px(1, 24, C_GREY, "SSD off, grey");                  -- 'S' col 0 row 3: .1111
        check_px(49, 48, C_CYAN, "TRG cyan");                       -- 'T' col 8 row 6: 11111
        check_px(1, 56, C_CYAN, "ERR cyan");                        -- 'E' col 0 row 7: 11111
        -- BCN = 12345: digits at cols 3..7 of row 1; '1' stem at cell col 3 -> x = 18+2
        check_px(20, 8, C_WHITE, "BCN count 12345 first digit");
        -- CMT = 7: cols 3..6 blank, '7' in col 7 -> x = 42..46 top row all set
        check_px(18, 16, x"0000", "CMT leading zero blanked");
        check_px(42, 16, C_WHITE, "CMT count 7");
        -- SFD = 0: only a '0' in col 7 of row 4 (y = 32): col 6 blank, col 7 row 0 = 01110
        check_px(36 + 2, 32, x"0000", "SFD col 6 blank");
        check_px(42 + 2, 32, C_WHITE, "SFD shows a single 0 (SW3 on, white)");
        -- SSD = 99999 saturated: col 3 '9' top row 01110 -> x = 18+1 .. ; SW2 is off so grey
        check_px(19, 24, C_GREY, "SSD saturated 99999 first digit");
        wait for 1 us;
        if lit < 300 then errors <= errors + 1; report "too few lit pixels" severity error; end if;
        wait for 1 us;
        if errors = 0 then
            report "TB PASSED";
        else
            report "TB FAILED with " & integer'image(errors) & " errors" severity failure;
        end if;
        done <= true;
        wait;
    end process;
end architecture sim;
