-- Differential Manchester (DME) bit recovery for 10BASE-T1S, sampled at
-- 100 MHz (8 samples per 80 ns bit cell).
--
-- The Pmod carries two RS-485 receivers on the same pair, one with A and B
-- swapped. Each has a fail-safe threshold just below 0 V, so
--
--   rx_i  (U1)  is low while the line is negative (below about -0.2 V)
--   rxn_i (U2)  is low while the line is positive (above about +0.2 V)
--   both high   the line is idle (nobody driving, within +-0.2 V)
--
-- One receiver alone cannot tell idle from one of the two driven levels, so
-- a transmission starting with that level would have no visible first edge.
-- With both, every transition on the wire asserts exactly one receiver:
-- idle -> +, - -> + assert U2; idle -> -, + -> - assert U1. Releasing the
-- line asserts neither, it just leaves both high; that is detected as a level
-- (IDLE_CLKS of both high) and the moment of release is used as the closing
-- edge of the last bit cell. Timing never depends on both receivers agreeing,
-- so their delay mismatch does not matter; it only shifts + -> - edges
-- relative to - -> + edges by the difference, a few ns.
--
-- Every bit cell starts with a transition; a 1 has a second transition 40 ns
-- later, a 0 has none. So the time between consecutive edges is either
-- ~40 ns (half cell) or ~80 ns (full cell):
--
--   long  edge-to-edge gap            -> bit 0  (cell boundary to boundary)
--   short gap starting at a boundary  -> first half of a 1, wait for the next
--   short gap starting mid-cell       -> bit 1  (back on a boundary)
--   long gap starting mid-cell        -> coding violation, resynchronise
--
-- The first edge after SILENCE is a cell boundary, which is also how symbol
-- alignment is found (every transmission starts from silence). SILENCE is
-- declared 30 ns after the line is released; as a safety net a line held at
-- one level for 160 ns is treated as silent too.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.t1s_pkg.all;

entity dme_rx is
    port (
        clk        : in  std_logic;
        rx_i       : in  std_logic;   -- U1 output: low while the line is negative
        rxn_i      : in  std_logic;   -- U2 output (A/B swapped): low while the line is positive
        bit_valid  : out std_logic := '0';   -- one clock per recovered bit
        bit_val    : out std_logic := '0';
        start      : out std_logic := '0';   -- first edge after silence (cell/symbol boundary)
        silent     : out std_logic := '0';   -- level: line idle (both receivers high)
        violation  : out std_logic := '0'  -- DME timing violation (pulse)
    );
end entity dme_rx;

architecture rtl of dme_rx is
    -- gaps up to and including this many clocks count as a half cell
    constant SHORT_MAX : natural := C_HALF_CLKS + 1;  -- 50 ns
    -- both receivers high for this long = the line was released. A + <-> -
    -- transition can show both high for a few ns while the level crosses the
    -- idle band, which the input filter and this count ride through.
    constant IDLE_CLKS : natural := 3;

    signal s0_rx, s1_rx, f_rx, f_rx_d     : std_logic := '1';
    signal s0_rxn, s1_rxn, f_rxn, f_rxn_d : std_logic := '1';
    signal gap      : unsigned(4 downto 0) := (others => '1');
    signal mid      : std_logic := '0';   -- '1': last edge was mid-cell
    signal silent_r : std_logic := '1';
    signal rel_pend : std_logic := '0';   -- line went idle, waiting IDLE_CLKS to confirm
    signal rel_cnt  : unsigned(1 downto 0) := (others => '0');
    signal gap_rel  : unsigned(4 downto 0) := (others => '0');   -- gap at the moment of release
    signal close_d  : std_logic := '0';   -- silence follows the closing bit one clock later
begin
    silent <= silent_r;

    process (clk)
        variable pos_r, neg_r, idle, released, ev, closing : std_logic;
        variable g : unsigned(gap'range);
    begin
        if rising_edge(clk) then
            bit_valid <= '0';
            bit_val   <= '0';
            start     <= '0';
            violation <= '0';

            -- two-stage synchronisers, then 2-sample agreement filters so a
            -- glitch shorter than 20 ns cannot produce an edge
            s0_rx  <= rx_i;  s1_rx  <= s0_rx;
            s0_rxn <= rxn_i; s1_rxn <= s0_rxn;
            if s1_rx = s0_rx   then f_rx  <= s1_rx;  end if;
            if s1_rxn = s0_rxn then f_rxn <= s1_rxn; end if;
            f_rx_d  <= f_rx;
            f_rxn_d <= f_rxn;

            -- the closing bit goes out first, silence one clock later, so
            -- the symbol assembler sees the bit before the line is declared idle
            close_d <= '0';
            if close_d = '1' then
                silent_r <= '1';
            end if;

            neg_r    := f_rx_d and not f_rx;             -- line just went negative
            pos_r    := f_rxn_d and not f_rxn;           -- line just went positive
            idle     := f_rx and f_rxn;
            released := idle and not (f_rx_d and f_rxn_d);

            -- an edge is either receiver asserting, or a confirmed release
            -- (processed IDLE_CLKS late with the gap it had at the time)
            ev := '0'; closing := '0'; g := gap;
            if pos_r = '1' or neg_r = '1' then
                ev := '1';
                rel_pend <= '0';
            elsif rel_pend = '1' then
                if idle = '0' then
                    rel_pend <= '0';                    -- was just a level crossing
                elsif rel_cnt = IDLE_CLKS - 2 then
                    ev := '1'; closing := '1'; g := gap_rel;
                    rel_pend <= '0';
                else
                    rel_cnt <= rel_cnt + 1;
                end if;
            elsif released = '1' and silent_r = '0' then
                rel_pend <= '1';
                rel_cnt  <= (others => '0');
                gap_rel  <= gap;
            end if;

            if ev = '1' then
                gap <= (others => '0');
                if closing = '1' then
                    -- the release completes the last cell
                    if g > SHORT_MAX and mid = '0' then
                        bit_valid <= '1'; bit_val <= '0';
                    elsif g <= SHORT_MAX and mid = '1' then
                        bit_valid <= '1'; bit_val <= '1';
                    else
                        violation <= '1';               -- released mid-cell
                    end if;
                    close_d <= '1';
                    mid     <= '0';
                elsif silent_r = '1' then
                    -- first edge of a transmission: a cell boundary
                    silent_r <= '0';
                    mid      <= '0';
                    start    <= '1';
                elsif g <= SHORT_MAX then
                    if mid = '0' then
                        mid <= '1';               -- first half of a 1
                    else
                        mid       <= '0';
                        bit_valid <= '1';
                        bit_val   <= '1';
                    end if;
                else
                    if mid = '0' then
                        bit_valid <= '1';
                        bit_val   <= '0';
                    else
                        -- a full cell cannot start mid-cell
                        violation <= '1';
                        mid       <= '0';
                    end if;
                end if;
            else
                if gap /= to_unsigned(2**gap'length - 1, gap'length) then
                    gap <= gap + 1;
                end if;
                -- safety net: a line held at one level (no DME) counts as silent
                if gap >= C_SILENCE_CLKS - 1 and silent_r = '0' then
                    silent_r <= '1';
                    mid      <= '0';
                    rel_pend <= '0';
                end if;
            end if;
        end if;
    end process;
end architecture rtl;
