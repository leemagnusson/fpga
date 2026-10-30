-- Differential Manchester (DME) bit recovery for 10BASE-T1S, sampled at
-- 100 MHz (8 samples per 80 ns bit cell).
--
-- The receiver on the Pmod turns the differential bus into one logic level;
-- only its transitions matter. Every bit cell starts with a transition; a 1
-- has a second transition 40 ns later, a 0 has none. So the time between
-- consecutive edges is either ~40 ns (half cell) or ~80 ns (full cell):
--
--   long  edge-to-edge gap            -> bit 0  (cell boundary to boundary)
--   short gap starting at a boundary  -> first half of a 1, wait for the next
--   short gap starting mid-cell       -> bit 1  (back on a boundary)
--   long gap starting mid-cell        -> coding violation, resynchronise
--
-- The first edge after SILENCE is a cell boundary, which is also how symbol
-- alignment is found (every transmission starts from silence). SILENCE is
-- declared after 160 ns without an edge; the shortest legal gap between
-- transmissions is 200 ns.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.t1s_pkg.all;

entity dme_rx is
    port (
        clk        : in  std_logic;
        rx_i       : in  std_logic;   -- asynchronous line level from the receiver
        bit_valid  : out std_logic := '0';   -- one clock per recovered bit
        bit_val    : out std_logic := '0';
        start      : out std_logic := '0';   -- first edge after silence (cell/symbol boundary)
        silent     : out std_logic := '0';   -- level: no edges for C_SILENCE_CLKS
        violation  : out std_logic := '0'  -- DME timing violation (pulse)
    );
end entity dme_rx;

architecture rtl of dme_rx is
    -- gaps up to and including this many clocks count as a half cell
    constant SHORT_MAX : natural := C_HALF_CLKS + 1;  -- 50 ns

    signal sync0, sync1, filt, filt_d : std_logic := '1';
    signal gap      : unsigned(4 downto 0) := (others => '1');
    signal mid      : std_logic := '0';   -- '1': last edge was mid-cell
    signal silent_r : std_logic := '1';
begin
    silent <= silent_r;

    process (clk)
        variable edge : std_logic;
    begin
        if rising_edge(clk) then
            bit_valid <= '0';
            bit_val   <= '0';
            start     <= '0';
            violation <= '0';

            -- two-stage synchroniser, then a 2-sample agreement filter so a
            -- glitch shorter than 20 ns cannot produce an edge
            sync0 <= rx_i;
            sync1 <= sync0;
            if sync1 = sync0 then
                filt <= sync1;
            end if;
            filt_d <= filt;
            edge := filt xor filt_d;

            if edge = '1' then
                gap <= (others => '0');
                if silent_r = '1' then
                    -- first edge of a transmission: a cell boundary
                    silent_r <= '0';
                    mid      <= '0';
                    start    <= '1';
                elsif gap <= SHORT_MAX then
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
                -- The last cell of a transmission has no following edge to
                -- complete it: a final 0 is a lone clock transition, a final 1
                -- has had its mid-cell transition. Emit it just before
                -- declaring silence. (If the receiver's fail-safe adds an edge
                -- when the driver releases the line, that edge completes the
                -- cell instead and this emits one spare bit, which the symbol
                -- assembler discards as a partial symbol at silence.)
                if gap = C_SILENCE_CLKS - 2 and silent_r = '0' then
                    bit_valid <= '1';
                    bit_val   <= mid;
                end if;
                if gap >= C_SILENCE_CLKS - 1 then
                    silent_r <= '1';
                    mid      <= '0';
                end if;
            end if;
        end if;
    end process;
end architecture rtl;
