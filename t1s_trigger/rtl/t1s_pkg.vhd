-- 10BASE-T1S (IEEE 802.3 Clause 147) line-coding constants shared by the
-- monitor and its testbench.
--
-- Sources: IEEE 802.3cg drafts (Clause 147 r2.0 comment resolution, Sept 2018;
-- D0.3, Nov 2017), the OPEN Alliance 10BASE-T1S PCS compliance test suite
-- v1.0 and the OPEN Alliance TC14/TC10 sleep/wake specification, which quotes
-- the 802.3-2022 Table 147-1 rows that were renamed after the draft. The
-- 5B value of 'S' (ESDJAB) does not appear in any public document we could
-- find; see C_SYM_S below.
--
-- Line coding summary:
--   * 12.5 MBd DME: a clock transition at the start of every 80 ns bit cell,
--     plus a data transition in the middle of the cell when the bit is 1.
--     Polarity is irrelevant. SILENCE is the absence of transitions.
--   * 5B symbols are sent LSB first.
--   * A packet is  J J H H  <12 scrambled preamble/SFD nibbles>  <scrambled
--     data nibbles, low nibble of each octet first>  T R   (T K = transmit
--     error, T S = jabber, R R = end of a burst packet, more follow).
--   * COMMIT is a run of J symbols (a packet's own two SYNCs then blend in).
--   * BEACON is a run of N symbols, nominally 20 bit times = 5 symbols.
--   * The scrambler is multiplicative, x^17 + x^14 + 1, applied to the 4B
--     data bits LSB first, before 4B/5B encoding. Special symbols are not
--     scrambled. The receiver discards 9 symbols after the second SSD while
--     the self-synchronising descrambler locks.

library ieee;
use ieee.std_logic_1164.all;

package t1s_pkg is

    -- Table 147-1, 5B codes written MSB..LSB (bit 4 downto 0)
    constant C_SYM_I : std_logic_vector(4 downto 0) := "11111"; -- SILENCE (never on the wire)
    constant C_SYM_J : std_logic_vector(4 downto 0) := "11000"; -- SYNC / COMMIT
    constant C_SYM_H : std_logic_vector(4 downto 0) := "00100"; -- SSD
    constant C_SYM_T : std_logic_vector(4 downto 0) := "01101"; -- ESD (also HB / SUSPEND)
    constant C_SYM_R : std_logic_vector(4 downto 0) := "00111"; -- ESDOK, and ESDBRS when it replaces T
    constant C_SYM_K : std_logic_vector(4 downto 0) := "10001"; -- ESDERR
    constant C_SYM_N : std_logic_vector(4 downto 0) := "01000"; -- BEACON
    -- ESDJAB. Not verifiable from public sources: 802.3cg-2019 added it after
    -- the last public draft. 11001 is one of the codes left unused by the
    -- draft table. Any other symbol following an ESD is reported as a
    -- protocol error, so a wrong guess here only moves jabber from the
    -- "ESDJAB" event to the "protocol error" event.
    constant C_SYM_S : std_logic_vector(4 downto 0) := "11001";

    type t_sym_kind is (SK_DATA, SK_J, SK_H, SK_T, SK_R, SK_K, SK_N, SK_S, SK_INVALID);

    -- 5B -> 4B. valid is '1' only for the 16 data codes.
    procedure decode_5b(signal_in : in  std_logic_vector(4 downto 0);
                        kind      : out t_sym_kind;
                        nibble    : out std_logic_vector(3 downto 0));

    -- 4B -> 5B (used by the testbench's transmitter model)
    function encode_4b(nibble : std_logic_vector(3 downto 0)) return std_logic_vector;

    -- Ethernet CRC-32, reflected form (as transmitted: LSB of each octet
    -- first). Feed octets with crc32_update; after the FCS has been fed the
    -- register equals C_CRC32_RESIDUE for a good frame.
    constant C_CRC32_INIT    : std_logic_vector(31 downto 0) := x"FFFFFFFF";
    constant C_CRC32_RESIDUE : std_logic_vector(31 downto 0) := x"DEBB20E3";
    function crc32_update(crc : std_logic_vector(31 downto 0);
                          nib : std_logic_vector(3 downto 0)) return std_logic_vector;

    -- Timing at the 100 MHz sample clock
    constant C_CLK_HZ          : natural := 100_000_000;
    constant C_BIT_CLKS        : natural := 8;   -- 80 ns bit cell
    constant C_HALF_CLKS       : natural := 4;   -- 40 ns data transition
    constant C_SILENCE_CLKS    : natural := 16;  -- 160 ns without an edge = SILENCE
    -- PLCA defaults (bit times are 100 ns, i.e. 10 clocks)
    constant C_PLCA_TO_CLKS     : natural := 32 * 10;  -- to_timer, 32 BT
    constant C_PLCA_BEACON_BT   : natural := 20;       -- beacon_timer, 20 BT
    constant C_PLCA_BURST_CLKS  : natural := 128 * 10; -- burst_timer, 128 BT

end package t1s_pkg;

package body t1s_pkg is

    procedure decode_5b(signal_in : in  std_logic_vector(4 downto 0);
                        kind      : out t_sym_kind;
                        nibble    : out std_logic_vector(3 downto 0)) is
    begin
        kind   := SK_INVALID;
        nibble := x"0";
        case signal_in is
            when "11110" => kind := SK_DATA; nibble := x"0";
            when "01001" => kind := SK_DATA; nibble := x"1";
            when "10100" => kind := SK_DATA; nibble := x"2";
            when "10101" => kind := SK_DATA; nibble := x"3";
            when "01010" => kind := SK_DATA; nibble := x"4";
            when "01011" => kind := SK_DATA; nibble := x"5";
            when "01110" => kind := SK_DATA; nibble := x"6";
            when "01111" => kind := SK_DATA; nibble := x"7";
            when "10010" => kind := SK_DATA; nibble := x"8";
            when "10011" => kind := SK_DATA; nibble := x"9";
            when "10110" => kind := SK_DATA; nibble := x"A";
            when "10111" => kind := SK_DATA; nibble := x"B";
            when "11010" => kind := SK_DATA; nibble := x"C";
            when "11011" => kind := SK_DATA; nibble := x"D";
            when "11100" => kind := SK_DATA; nibble := x"E";
            when "11101" => kind := SK_DATA; nibble := x"F";
            when C_SYM_J => kind := SK_J;
            when C_SYM_H => kind := SK_H;
            when C_SYM_T => kind := SK_T;
            when C_SYM_R => kind := SK_R;
            when C_SYM_K => kind := SK_K;
            when C_SYM_N => kind := SK_N;
            when C_SYM_S => kind := SK_S;
            when others  => kind := SK_INVALID;
        end case;
    end procedure;

    function encode_4b(nibble : std_logic_vector(3 downto 0)) return std_logic_vector is
    begin
        case nibble is
            when x"0" => return "11110";
            when x"1" => return "01001";
            when x"2" => return "10100";
            when x"3" => return "10101";
            when x"4" => return "01010";
            when x"5" => return "01011";
            when x"6" => return "01110";
            when x"7" => return "01111";
            when x"8" => return "10010";
            when x"9" => return "10011";
            when x"A" => return "10110";
            when x"B" => return "10111";
            when x"C" => return "11010";
            when x"D" => return "11011";
            when x"E" => return "11100";
            when others => return "11101";
        end case;
    end function;

    function crc32_update(crc : std_logic_vector(31 downto 0);
                          nib : std_logic_vector(3 downto 0)) return std_logic_vector is
        variable c : std_logic_vector(31 downto 0) := crc;
        constant POLY : std_logic_vector(31 downto 0) := x"EDB88320"; -- 0x04C11DB7 reflected
    begin
        for i in 0 to 3 loop
            if (c(0) xor nib(i)) = '1' then
                c := ('0' & c(31 downto 1)) xor POLY;
            else
                c := '0' & c(31 downto 1);
            end if;
        end loop;
        return c;
    end function;

end package body t1s_pkg;
