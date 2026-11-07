-- Timing-jitter statistics of a 10BASE-T1S transmission, in the 125 MHz
-- processing clock domain.
--
-- Input: eight 1 ns samples per clock of each Pmod receiver (see dme_rx.vhd
-- for what the two receivers mean). An "edge" is a receiver asserting (going
-- low): that is the moment the line crosses the receiver's threshold in the
-- new direction, and exactly one receiver asserts for every transition on
-- the wire. Deassertions are ignored (they happen a few ns later, while the
-- level crosses the idle band).
--
-- Every edge gets a 1 ns timestamp. DME transitions are 40 or 80 ns apart,
-- so each interval is classified as a half cell (40) or a full cell (80) and
-- its error e = interval - nominal is taken. To be insensitive to anything
-- deterministic (duty-cycle distortion, the delay difference between the two
-- receivers, the transmitter's clock offset) the statistic is the difference
-- d between an interval's error and the previous error of the same kind,
-- "kind" being the pair (half/full, edge polarity). For independent edge
-- jitter of variance s^2 and 1 ns sampling:
--
--     var(d) = 4 s^2 + 1/3        (ns^2)
--
-- so the sum S of d^2 and the count N over a transmission give s without a
-- mean to subtract. S and N are handed over at the end of the transmission
-- (no edge for IDLE_CLKS clocks) with a toggle; sqi_calc.vhd turns them into
-- an SQI+ level in the 100 MHz domain.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity edge_time is
    generic (
        IDLE_CLKS : natural := 24          -- 192 ns without an edge ends the transmission
    );
    port (
        clk      : in  std_logic;                     -- 125 MHz
        s_rx     : in  std_logic_vector(7 downto 0);  -- receiver U1 samples, (0) earliest
        s_rxn    : in  std_logic_vector(7 downto 0);  -- receiver U2 samples
        -- totals of the last transmission, valid when tot_tgl changes
        tot_s    : out unsigned(27 downto 0) := (others => '0');   -- sum of d^2 (ns^2)
        tot_n    : out unsigned(13 downto 0) := (others => '0');   -- number of d
        tot_tgl  : out std_logic := '0';
        -- debug
        edge     : out std_logic := '0'               -- one clock per accepted edge
    );
end entity edge_time;

architecture rtl of edge_time is
    constant HALF_NS   : natural := 40;
    constant FULL_NS   : natural := 80;
    constant GLITCH_NS : natural := 16;   -- an assertion sooner than this after the last one is noise

    signal prev_rx, prev_rxn : std_logic := '1';
    -- stage 1: edge found in this clock
    signal e1_hit : std_logic := '0';
    signal e1_pos : unsigned(2 downto 0) := (others => '0');
    signal e1_pol : std_logic := '0';           -- '1': line went positive (U2 asserted)
    -- timestamps
    signal clk_cnt : unsigned(14 downto 0) := (others => '0');
    signal last_ts : unsigned(17 downto 0) := (others => '0');
    signal have_ts : std_logic := '0';
    -- stage 2: interval
    signal e2_hit  : std_logic := '0';
    signal e2_pol  : std_logic := '0';
    signal e2_int  : unsigned(17 downto 0) := (others => '0');
    -- stage 3: classified error
    signal e3_hit  : std_logic := '0';
    signal e3_kind : unsigned(1 downto 0) := (others => '0');   -- (full?, pol)
    signal e3_err  : signed(6 downto 0) := (others => '0');     -- -64..63 ns, saturated
    -- stage 4: difference to the previous error of the same kind
    type t_err4 is array (0 to 3) of signed(6 downto 0);
    signal prev_err   : t_err4 := (others => (others => '0'));
    signal prev_valid : std_logic_vector(3 downto 0) := (others => '0');
    signal e4_hit  : std_logic := '0';
    signal e4_d    : signed(7 downto 0) := (others => '0');
    -- stage 5: square
    signal e5_hit  : std_logic := '0';
    signal e5_sq   : unsigned(13 downto 0) := (others => '0');
    -- accumulators
    signal acc_s   : unsigned(27 downto 0) := (others => '0');
    signal acc_n   : unsigned(13 downto 0) := (others => '0');
    signal idle_cnt : unsigned(7 downto 0) := (others => '0');
    signal in_tx    : std_logic := '0';
    signal flush    : std_logic := '0';
begin
    process (clk)
        variable a_rx, a_rxn : std_logic_vector(7 downto 0);
        variable p_rx, p_rxn : std_logic;
        variable hit : std_logic;
        variable pos : unsigned(2 downto 0);
        variable pol : std_logic;
        variable ts  : unsigned(17 downto 0);
        variable d   : signed(7 downto 0);
        variable err : integer;
    begin
        if rising_edge(clk) then
            -- ---- stage 1: first assertion in this clock ----------------------
            p_rx := prev_rx; p_rxn := prev_rxn;
            hit := '0'; pos := "000"; pol := '0';
            for i in 0 to 7 loop
                a_rx(i)  := p_rx  and not s_rx(i);
                a_rxn(i) := p_rxn and not s_rxn(i);
                p_rx := s_rx(i); p_rxn := s_rxn(i);
            end loop;
            for i in 7 downto 0 loop            -- lowest index wins
                if a_rx(i) = '1' or a_rxn(i) = '1' then
                    hit := '1'; pos := to_unsigned(i, 3); pol := a_rxn(i);
                end if;
            end loop;
            prev_rx  <= s_rx(7);
            prev_rxn <= s_rxn(7);
            e1_hit <= hit; e1_pos <= pos; e1_pol <= pol;
            clk_cnt <= clk_cnt + 1;

            -- ---- stage 2: timestamp and interval ---------------------------------
            e2_hit <= '0';
            edge   <= '0';
            if e1_hit = '1' then
                ts := (clk_cnt - 1) & e1_pos;          -- clk_cnt already advanced
                if have_ts = '1' and ts - last_ts < GLITCH_NS then
                    null;                               -- noise: keep the earlier edge
                else
                    if have_ts = '1' then
                        e2_hit <= '1';
                        e2_int <= ts - last_ts;
                        e2_pol <= e1_pol;
                    end if;
                    last_ts <= ts;
                    have_ts <= '1';
                    edge    <= '1';
                end if;
                idle_cnt <= (others => '0');
                in_tx    <= '1';
            elsif idle_cnt /= 255 then
                idle_cnt <= idle_cnt + 1;
            end if;

            -- ---- stage 3: half or full cell, error vs nominal --------------------
            e3_hit <= '0';
            if e2_hit = '1' then
                if e2_int < (HALF_NS + FULL_NS) / 2 then
                    err := to_integer(e2_int) - HALF_NS;
                    e3_kind <= '0' & e2_pol;
                    e3_hit  <= '1';
                elsif e2_int < FULL_NS + HALF_NS / 2 then
                    err := to_integer(e2_int) - FULL_NS;
                    e3_kind <= '1' & e2_pol;
                    e3_hit  <= '1';
                else
                    err := 0;                           -- not DME (gap), ignore
                end if;
                if err > 63 then err := 63; elsif err < -64 then err := -64; end if;
                e3_err <= to_signed(err, 7);
            end if;

            -- ---- stage 4: difference to the previous error of the same kind ------
            e4_hit <= '0';
            if e3_hit = '1' then
                d := resize(e3_err, 8) - resize(prev_err(to_integer(e3_kind)), 8);
                e4_d   <= d;
                e4_hit <= prev_valid(to_integer(e3_kind));
                prev_err(to_integer(e3_kind))   <= e3_err;
                prev_valid(to_integer(e3_kind)) <= '1';
            end if;

            -- ---- stage 5: square -------------------------------------------------
            e5_hit <= e4_hit;
            e5_sq  <= resize(unsigned(e4_d * e4_d), 14);

            -- ---- accumulate, hand over at the end of the transmission ------------
            if e5_hit = '1' then
                if acc_s(27) = '0' then                 -- keep well clear of overflow
                    acc_s <= acc_s + e5_sq;
                end if;
                if acc_n /= 2**14 - 1 then
                    acc_n <= acc_n + 1;
                end if;
            end if;

            flush <= '0';
            if in_tx = '1' and idle_cnt = IDLE_CLKS then
                flush <= '1';                           -- one clock after the pipeline drained
                in_tx <= '0';
                have_ts <= '0';
                prev_valid <= (others => '0');
            end if;
            if flush = '1' then
                tot_s   <= acc_s;
                tot_n   <= acc_n;
                tot_tgl <= not tot_tgl;
                acc_s   <= (others => '0');
                acc_n   <= (others => '0');
            end if;
        end if;
    end process;
end architecture rtl;
