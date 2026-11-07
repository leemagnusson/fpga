-- Turns the per-transmission jitter totals from edge_time.vhd into a 5-bit
-- SQI+ level (0 = worst .. 31 = best), on the 100 MHz clock.
--
-- edge_time delivers S = sum of d^2 and N = count, with var(d) = 4 s^2 + 1/3
-- for edge jitter s (rms, ns) at 1 ns sampling. The level is the largest k
-- such that s < s_k, where s_k is the jitter the LAN8670 Rev D0 maps to
-- SQI+ = k (measured on the bench, arb/README.md: SQI+ = 33 - 8.8 s):
--
--     s_k = (33 - k) / 8.8 ns,   so   s < s_k  <=>  S < N * (4 s_k^2 + 1/3)
--
-- A floor s_f (generic, ns^2 x 256) for the receivers' own jitter is
-- subtracted inside the bracket. No division: at most 32 compare-with-product
-- steps per transmission. var_x256 = S*256/N (a restoring divider, for the
-- display and for calibrating the floor) follows a few hundred ns later.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;

entity sqi_calc is
    generic (
        FLOOR2_X256 : natural := 0        -- receiver jitter floor squared, ns^2 x 256
    );
    port (
        clk       : in  std_logic;                    -- 100 MHz
        -- from edge_time (125 MHz domain), stable while tot_tgl is steady
        tot_s     : in  unsigned(27 downto 0);
        tot_n     : in  unsigned(13 downto 0);
        tot_tgl   : in  std_logic;
        min_n     : in  unsigned(13 downto 0) := to_unsigned(64, 14);  -- ignore shorter transmissions
        -- result
        sqi       : out unsigned(4 downto 0) := (others => '0');
        sqi_valid : out std_logic := '0';              -- one clock when sqi updates
        var_x256  : out unsigned(19 downto 0) := (others => '0');  -- S*256/N (ns^2 x 256), updated after sqi
        var_valid : out std_logic := '0'
    );
end entity sqi_calc;

architecture rtl of sqi_calc is
    type t_thr is array (0 to 31) of unsigned(15 downto 0);
    function thresholds return t_thr is
        variable t : t_thr;
        variable s2, c : real;
    begin
        for k in 0 to 31 loop
            s2 := ((33.0 - real(k)) / 8.8) ** 2 - real(FLOOR2_X256) / 256.0;
            if s2 < 0.0 then s2 := 0.0; end if;
            c := 4.0 * s2 + 1.0 / 3.0;
            t(k) := to_unsigned(integer(round(c * 256.0)), 16);
        end loop;
        return t;
    end function;
    constant THR : t_thr := thresholds;

    signal tgl_s0, tgl_s1, tgl_s2 : std_logic := '0';
    signal s_lat : unsigned(35 downto 0) := (others => '0');   -- S * 256
    signal n_lat : unsigned(13 downto 0) := (others => '0');
    signal busy  : std_logic := '0';
    signal k     : unsigned(4 downto 0) := (others => '0');
    signal prod  : unsigned(29 downto 0) := (others => '0');   -- N * THR(k), registered
    signal cmp   : std_logic := '0';                           -- prod is valid for k this cycle
    -- restoring divider for var_x256
    signal dv_rem  : unsigned(36 downto 0) := (others => '0');
    signal dv_q    : unsigned(35 downto 0) := (others => '0');
    signal dv_cnt  : unsigned(5 downto 0) := (others => '0');
    signal dv_busy : std_logic := '0';
begin
    process (clk)
        variable r : unsigned(36 downto 0);
    begin
        if rising_edge(clk) then
            tgl_s0 <= tot_tgl; tgl_s1 <= tgl_s0; tgl_s2 <= tgl_s1;
            sqi_valid <= '0';
            var_valid <= '0';

            if busy = '0' then
                if tgl_s2 /= tgl_s1 and tot_n >= min_n then
                    s_lat <= resize(tot_s, 36) sll 8;
                    n_lat <= tot_n;
                    k     <= to_unsigned(31, 5);
                    busy  <= '1';
                    cmp   <= '0';
                    dv_rem  <= (others => '0');
                    dv_q    <= resize(tot_s, 36) sll 8;
                    dv_cnt  <= (others => '0');
                    dv_busy <= '1';
                end if;
            else
                -- largest k with S*256 < N * THR(k), from the best level down;
                -- two clocks per k: multiply, then compare
                prod <= n_lat * THR(to_integer(k));
                cmp  <= not cmp;
                if cmp = '1' then
                    if s_lat < resize(prod, 36) then
                        sqi <= k;
                        sqi_valid <= '1';
                        busy <= '0';
                    elsif k = 0 then
                        sqi <= (others => '0');
                        sqi_valid <= '1';
                        busy <= '0';
                    else
                        k <= k - 1;
                    end if;
                end if;
            end if;

            if dv_busy = '1' then
                r := dv_rem(35 downto 0) & dv_q(35);
                if r >= resize(n_lat, 37) then
                    r := r - resize(n_lat, 37);
                    dv_q <= dv_q(34 downto 0) & '1';
                else
                    dv_q <= dv_q(34 downto 0) & '0';
                end if;
                dv_rem <= r;
                if dv_cnt = 35 then
                    dv_busy   <= '0';
                    var_valid <= '1';
                else
                    dv_cnt <= dv_cnt + 1;
                end if;
            end if;
            if var_valid = '1' then
                var_x256 <= dv_q(19 downto 0);
            end if;
        end if;
    end process;
end architecture rtl;
