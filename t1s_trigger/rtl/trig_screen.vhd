-- The status picture for the Pmod OLEDrgb: 16 x 8 characters of 6 x 8 pixels
-- on the 96 x 64 panel.
--
--   row 0   100NS ID=5 PLCA     TRIG0 pulse width (SW10), node ID (SW15..12),
--                               PLCA (green, beacons seen) or CSMA (grey)
--   row 1-6 BCN12345 JAB12345   one entry per switch-selectable trigger: name
--           CMT12345 BRS12345   and events in the last second. White when its
--           SSD12345 CRC12345   switch is on, grey when off.
--           SFD12345 PRT12345
--           EOK12345 ID512345   (ID5: packets from node SW15..12, SW11)
--           EER12345 TRG12345   TRG: TRIG0 pulses actually produced, cyan
--   row 7   ERR12345 HB 12345   any error (TRIG3), heartbeat runs; cyan/white
--
-- Rate inputs are 5-digit BCD (see bcd_rate), index: 0 beacon, 1 commit,
-- 2 ssd, 3 sfd, 4 esd_ok, 5 esd_err, 6 esd_jab, 7 burst, 8 crc_err,
-- 9 proto_err|runt, 10 node, 11 trig0, 12 any_err, 13 hb.
--
-- The pixel interface matches oled_ssd1331: px_rgb answers px_x/px_y two
-- clocks later.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package trig_screen_pkg is
    subtype t_bcd5 is std_logic_vector(19 downto 0);
    type t_rates is array (natural range <>) of t_bcd5;
    constant N_RATES : natural := 14;
end package trig_screen_pkg;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.oled_font_pkg.all;
use work.trig_screen_pkg.all;

entity trig_screen is
    port (
        clk         : in  std_logic;
        sw          : in  std_logic_vector(15 downto 0);
        plca_synced : in  std_logic;
        rates       : in  t_rates(0 to N_RATES - 1);
        px_x        : in  unsigned(6 downto 0);
        px_y        : in  unsigned(5 downto 0);
        px_rgb      : out std_logic_vector(15 downto 0) := (others => '0')
    );
end entity trig_screen;

architecture rtl of trig_screen is
    constant COLS : natural := 16;
    constant ROWS : natural := 8;

    -- colour indices
    constant C_OFF    : natural := 0;
    constant C_GREY   : natural := 1;
    constant C_WHITE  : natural := 2;
    constant C_YELLOW : natural := 3;
    constant C_CYAN   : natural := 4;
    constant C_GREEN  : natural := 5;
    type t_palette is array (0 to 7) of std_logic_vector(15 downto 0);
    constant PALETTE : t_palette := (
        x"0000", x"4208", x"FFFF", x"FFE0", x"07FF", x"07E0", x"0000", x"0000");

    type t_chars  is array (0 to COLS * ROWS - 1) of t_char;
    type t_colors is array (0 to COLS * ROWS - 1) of natural range 0 to 7;
    constant SPACE : t_char := ch(' ');
    signal scr_ch  : t_chars  := (others => SPACE);
    signal scr_col : t_colors := (others => C_OFF);

    -- All text is turned into character codes at elaboration (ch() is a search
    -- and must never see a run-time argument: that synthesises to comparators).
    type t_text is array (natural range <>) of t_char;
    function text(s : string) return t_text is
        variable r : t_text(0 to s'length - 1);
    begin
        for i in s'range loop
            r(i - s'low) := ch(s(i));
        end loop;
        return r;
    end function;
    constant HDR_NS : t_text(0 to 15) := text("100NS ID=  PLCA ");
    constant HDR_US : t_text(0 to 15) := text("  1US ID=  PLCA ");
    constant CSMA   : t_text(0 to 3)  := text("CSMA");

    -- the 14 entries: name, rate index, switch (-1 = always on), colour when on
    type t_entry is record
        name : t_text(0 to 2);
        rate : natural;
        sw   : integer;
        col  : natural;
    end record;
    type t_entries is array (0 to 13) of t_entry;
    constant ENTRIES : t_entries := (
        (text("BCN"), 0, 0, C_WHITE), (text("CMT"), 1, 1, C_WHITE), (text("SSD"), 2, 2, C_WHITE),
        (text("SFD"), 3, 3, C_WHITE), (text("EOK"), 4, 4, C_WHITE), (text("EER"), 5, 5, C_WHITE),
        (text("JAB"), 6, 6, C_WHITE), (text("BRS"), 7, 7, C_WHITE), (text("CRC"), 8, 8, C_WHITE),
        (text("PRT"), 9, 9, C_WHITE), (text("ID "), 10, 11, C_WHITE), (text("TRG"), 11, -1, C_CYAN),
        (text("ERR"), 12, -1, C_CYAN), (text("HB "), 13, -1, C_WHITE));
    -- entry i sits at (row, col): 0..5 left column rows 1..6, 6..11 right column, 12/13 row 7
    function entry_pos(i : natural) return natural is
    begin
        if i < 6 then return (i + 1) * COLS;
        elsif i < 12 then return (i - 6 + 1) * COLS + 8;
        elsif i = 12 then return 7 * COLS;
        else return 7 * COLS + 8;
        end if;
    end function;

    -- '0'..'9' are codes 0..9 and 'A'..'F' codes 10..15 in the font, so a hex
    -- digit is its own character code (checked below).
    function hex_char(n : unsigned(3 downto 0)) return t_char is
    begin
        return to_integer(n);
    end function;

    -- pixel pipeline. x -> (character column, pixel within the cell) is a
    -- constant table built at elaboration: integer division on a signal would
    -- synthesise to a 32-bit divider.
    type t_xmap is record
        col : natural range 0 to 15;
        cx  : natural range 0 to 7;
    end record;
    type t_xmaps is array (0 to 127) of t_xmap;
    function make_xmap return t_xmaps is
        variable r : t_xmaps;
    begin
        for x in r'range loop
            r(x).col := (x / 6) mod 16;
            r(x).cx  := x mod 6;
        end loop;
        return r;
    end function;
    constant XMAP : t_xmaps := make_xmap;

    signal glyph_row  : std_logic_vector(4 downto 0) := (others => '0');
    signal cx_r       : natural range 0 to 7 := 0;
    signal gy_valid   : std_logic := '0';
    signal col_r      : natural range 0 to 7 := 0;
begin
    assert ch('0') = 0 and ch('9') = 9 and ch('A') = 10 and ch('F') = 15
        report "font order changed: hex_char assumes 0-9 A-F at codes 0..15" severity failure;

    -- ---- build the character screen (changes only with the counters/switches)
    process (clk)
        variable p    : natural;
        variable e    : t_entry;
        variable lit  : boolean;
        variable c    : natural;
        variable blank : boolean;
        variable dgt  : unsigned(3 downto 0);
        variable hdr  : t_text(0 to 15);
    begin
        if rising_edge(clk) then
            scr_ch  <= (others => SPACE);
            scr_col <= (others => C_OFF);

            -- header
            if sw(10) = '1' then hdr := HDR_US; else hdr := HDR_NS; end if;
            if plca_synced = '0' then hdr(11 to 14) := CSMA; end if;
            for i in 0 to 15 loop
                scr_ch(i)  <= hdr(i);
                scr_col(i) <= C_YELLOW;
            end loop;
            scr_ch(9) <= hex_char(unsigned(sw(15 downto 12)));
            if plca_synced = '1' then
                for i in 11 to 14 loop scr_col(i) <= C_GREEN; end loop;
            else
                for i in 11 to 14 loop scr_col(i) <= C_GREY; end loop;
            end if;

            -- entries
            for i in ENTRIES'range loop
                e := ENTRIES(i);
                p := entry_pos(i);
                if e.sw < 0 then
                    lit := true;
                else
                    lit := sw(e.sw) = '1';
                end if;
                if lit then c := e.col; else c := C_GREY; end if;
                for k in 0 to 2 loop
                    scr_ch(p + k)  <= e.name(k);
                    scr_col(p + k) <= c;
                end loop;
                if i = 10 then                              -- "ID5"
                    scr_ch(p + 2) <= hex_char(unsigned(sw(15 downto 12)));
                end if;
                -- five digits, leading zeros blanked
                blank := true;
                for d in 4 downto 0 loop
                    dgt := unsigned(rates(e.rate)(4 * d + 3 downto 4 * d));
                    if dgt /= 0 or d = 0 then blank := false; end if;
                    if blank then
                        scr_ch(p + 3 + (4 - d)) <= SPACE;
                    else
                        scr_ch(p + 3 + (4 - d)) <= hex_char(dgt);
                    end if;
                    scr_col(p + 3 + (4 - d)) <= c;
                end loop;
            end loop;
        end if;
    end process;

    -- ---- pixel lookup: stage 1 character cell, stage 2 glyph bit --------------
    process (clk)
        variable m   : t_xmap;
        variable gy  : natural range 0 to 7;
        variable idx : natural range 0 to COLS * ROWS - 1;
    begin
        if rising_edge(clk) then
            m   := XMAP(to_integer(px_x));
            gy  := to_integer(px_y(2 downto 0));
            idx := to_integer(px_y(5 downto 3) & to_unsigned(m.col, 4));   -- row * 16 + col
            if gy < 7 and px_x < 96 then
                glyph_row <= FONT(scr_ch(idx))(gy);
                gy_valid  <= '1';
            else
                glyph_row <= (others => '0');
                gy_valid  <= '0';
            end if;
            cx_r  <= m.cx;
            col_r <= scr_col(idx);

            if cx_r < 5 and gy_valid = '1' and glyph_row(4 - cx_r) = '1' then
                px_rgb <= PALETTE(col_r);
            else
                px_rgb <= PALETTE(C_OFF);
            end if;
        end if;
    end process;
end architecture rtl;
