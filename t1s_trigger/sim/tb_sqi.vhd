-- Self-checking testbench for the timing-jitter SQI+ (rtl/t1s_sqi.vhd).
--
-- A behavioural DME transmitter sends random bit streams whose transition
-- times carry Gaussian jitter of a chosen rms value, through the model of the
-- two fail-safe receivers (optionally with a fixed delay difference between
-- them), into t1s_sqi with its simulation clocks. After each transmission the
-- reported SQI+ must match the LAN8670-calibrated scale within one step.
-- Run: part of sim/run.sh; prints "TB PASSED".
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;
use std.env.all;

entity tb_sqi is
end entity tb_sqi;

architecture sim of tb_sqi is
    constant HALF : time := 40 ns;

    signal clk : std_logic := '0';
    signal clk_fast, clk_f90, clk_div, locked : std_logic;
    signal pol, driving : std_logic := '0';
    signal skew : time := 0 ns;             -- extra delay of the "positive" receiver
    signal n_raw, p_raw : std_logic;
    signal line_n, line_p : std_logic;

    signal sqi : unsigned(4 downto 0);
    signal sqi_valid, var_valid, edge_dbg : std_logic;
    signal var_x256 : unsigned(19 downto 0);
    signal n_valid : natural := 0;
    signal errors  : natural := 0;
    signal done    : boolean := false;
begin
    clk <= not clk after 5 ns when not done;

    u_clk : entity work.clk_gen
        generic map (G_SIM => true)
        port map (clk_in => clk, clk_fast => clk_fast, clk_f90 => clk_f90, clk_div => clk_div, locked => locked);

    -- receivers: U1 low while the line is negative, U2 low while positive
    n_raw <= '0' when driving = '1' and pol = '0' else '1';
    p_raw <= '0' when driving = '1' and pol = '1' else '1';
    line_n <= n_raw;
    line_p <= transport p_raw after skew;

    dut : entity work.t1s_sqi
        generic map (G_SIM => true)
        port map (clk => clk, clk_fast => clk_fast, clk_f90 => clk_f90, clk_div => clk_div,
                  rx_i => line_n, rxn_i => line_p, rx_o => open, rxn_o => open,
                  sqi => sqi, sqi_valid => sqi_valid, var_x256 => var_x256,
                  var_valid => var_valid, edge_dbg => edge_dbg);

    process (clk)
    begin
        if rising_edge(clk) and sqi_valid = '1' then
            n_valid <= n_valid + 1;
        end if;
    end process;

    process
        variable seed1 : positive := 7;
        variable seed2 : positive := 11;
        variable u1, u2, g : real;
        variable n_prev, n_now : real;
        variable expect_lo, expect_hi : integer;
        variable n0 : natural;

        -- one Gaussian sample (Box-Muller)
        impure function gauss return real is
        begin
            uniform(seed1, seed2, u1);
            uniform(seed1, seed2, u2);
            if u1 < 1.0e-12 then u1 := 1.0e-12; end if;
            return sqrt(-2.0 * log(u1)) * cos(2.0 * math_pi * u2);
        end function;

        -- random bits, DME, each transition displaced by N(0, sigma)
        procedure send_bits(nbits : natural; sigma_ns : real) is
            variable b : real;
        begin
            n_prev := 0.0;
            for i in 1 to nbits loop
                uniform(seed1, seed2, b);
                n_now := gauss * sigma_ns;
                pol <= not pol; driving <= '1';
                wait for HALF + (n_now - n_prev) * 1 ns;
                n_prev := n_now;
                if b < 0.5 then
                    n_now := gauss * sigma_ns;
                    pol <= not pol;
                    wait for HALF + (n_now - n_prev) * 1 ns;
                    n_prev := n_now;
                end if;
            end loop;
            wait for HALF;
            driving <= '0';
        end procedure;

        -- expected SQI+ for jitter s: largest k with s < (33 - k) / 8.8
        function expected(sigma_ns : real) return integer is
            variable k : integer;
        begin
            k := integer(floor(33.0 - 8.8 * sigma_ns - 1.0e-9));
            if k > 31 then k := 31; end if;
            if k < 0 then k := 0; end if;
            return k;
        end function;

        procedure run_case(name : string; sigma_ns : real; tol : integer := 1) is
            variable exp_k : integer;
        begin
            n0 := n_valid;
            send_bits(1200, sigma_ns);
            wait for 2 us;
            exp_k := expected(sigma_ns);
            if n_valid /= n0 + 1 then
                report name & ": expected one SQI result, got " & integer'image(n_valid - n0) severity error;
                errors <= errors + 1;
            elsif abs(to_integer(sqi) - exp_k) > tol then
                report name & ": SQI+ " & integer'image(to_integer(sqi)) & ", expected " &
                       integer'image(exp_k) & " (var_x256 " & integer'image(to_integer(var_x256)) & ")"
                       severity error;
                errors <= errors + 1;
            else
                report name & ": SQI+ " & integer'image(to_integer(sqi)) & " (expected " &
                       integer'image(exp_k) & "), S/N = " &
                       real'image(real(to_integer(var_x256)) / 256.0) & " ns^2";
            end if;
            wait for 0 ns;
        end procedure;
    begin
        wait for 1 us;
        run_case("clean",          0.0);
        run_case("0.5 ns",         0.5);
        run_case("1 ns",           1.0);
        run_case("2 ns",           2.0);
        run_case("3 ns",           3.0);
        run_case("4 ns",           4.0);
        run_case("clean again",    0.0);
        -- a fixed 4 ns delay difference between the receivers must not count as jitter
        skew <= 4 ns;
        run_case("clean, 4 ns receiver skew", 0.0);
        run_case("1 ns, 4 ns receiver skew",  1.0);
        skew <= 0 ns;
        -- a transmission too short for a result (below min_n) must be ignored
        n0 := n_valid;
        send_bits(20, 0.0);
        wait for 2 us;
        if n_valid /= n0 then
            report "short transmission produced a result" severity error;
            errors <= errors + 1;
            wait for 0 ns;
        end if;

        if errors = 0 then
            report "TB PASSED";
        else
            report integer'image(errors) & " checks failed" severity failure;
        end if;
        done <= true;
        wait for 1 ns;
        finish;                       -- the DUT's simulation clocks run forever otherwise
    end process;
end architecture sim;
