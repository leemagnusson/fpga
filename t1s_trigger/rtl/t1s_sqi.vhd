-- Timing-jitter SQI+ for 10BASE-T1S: the two Pmod receiver outputs are
-- oversampled at 1 ns, every transmission's edge-interval statistics are
-- accumulated (edge_time.vhd) and mapped to a 0..31 level (sqi_calc.vhd) on
-- the same scale as the LAN8670's DCQ SQI+. One result per transmission,
-- i.e. per frame, instead of the ~29k frames a LAN8650 needs.
--
-- rx_o / rxn_o are the pass-through pins for the existing 100 MHz decoder
-- (the ISERDES owns the pad, so the decoder takes the signal from here).
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity t1s_sqi is
    generic (
        G_SIM       : boolean := false;
        FLOOR2_X256 : natural := 0        -- receiver jitter floor squared, ns^2 x 256
    );
    port (
        clk        : in  std_logic;       -- 100 MHz
        clk_fast   : in  std_logic;       -- 250 MHz
        clk_f90    : in  std_logic;       -- 250 MHz + 90 degrees
        clk_div    : in  std_logic;       -- 125 MHz, aligned with clk_fast
        rx_i       : in  std_logic;       -- Pmod receiver U1 pin
        rxn_i      : in  std_logic;       -- Pmod receiver U2 pin
        rx_o       : out std_logic;       -- pass-through for dme_rx
        rxn_o      : out std_logic;
        min_n      : in  unsigned(13 downto 0) := to_unsigned(64, 14);
        sqi        : out unsigned(4 downto 0);
        sqi_valid  : out std_logic;
        var_x256   : out unsigned(19 downto 0);
        var_valid  : out std_logic;
        edge_dbg   : out std_logic
    );
end entity t1s_sqi;

architecture rtl of t1s_sqi is
    signal s_rx, s_rxn : std_logic_vector(7 downto 0);
    signal tot_s   : unsigned(27 downto 0);
    signal tot_n   : unsigned(13 downto 0);
    signal tot_tgl : std_logic;
begin
    u_os_rx : entity work.oversample_in
        generic map (G_SIM => G_SIM)
        port map (clk => clk_fast, clk90 => clk_f90, clk_div => clk_div, d => rx_i, o => rx_o, q => s_rx);

    u_os_rxn : entity work.oversample_in
        generic map (G_SIM => G_SIM)
        port map (clk => clk_fast, clk90 => clk_f90, clk_div => clk_div, d => rxn_i, o => rxn_o, q => s_rxn);

    u_edge : entity work.edge_time
        port map (clk => clk_div, s_rx => s_rx, s_rxn => s_rxn,
                  tot_s => tot_s, tot_n => tot_n, tot_tgl => tot_tgl, edge => edge_dbg);

    u_calc : entity work.sqi_calc
        generic map (FLOOR2_X256 => FLOOR2_X256)
        port map (clk => clk, tot_s => tot_s, tot_n => tot_n, tot_tgl => tot_tgl, min_n => min_n,
                  sqi => sqi, sqi_valid => sqi_valid, var_x256 => var_x256, var_valid => var_valid);
end architecture rtl;
