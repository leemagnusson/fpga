-- Basys 3 top level: 10BASE-T1S line monitor with switch-selected trigger
-- outputs. See README.md for the switch, LED and Pmod assignments.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.t1s_pkg.all;
use work.trig_screen_pkg.all;

entity top is
    generic (
        OLED_CLKS_PER_MS : positive := 100_000;   -- display timing (shrunk by the simulation)
        OLED_SPI_DIV     : positive := 16;
        G_SIM            : boolean  := false;     -- behavioural clocks / samplers instead of MMCM and ISERDES
        SQI_FLOOR2_X256  : natural  := 0          -- receiver jitter floor for the SQI+ scale, ns^2 x 256
    );
    port (
        clk        : in  std_logic;                      -- 100 MHz
        sw         : in  std_logic_vector(15 downto 0);
        led        : out std_logic_vector(15 downto 0);
        btnC, btnU, btnD, btnL, btnR : in std_logic;
        seg        : out std_logic_vector(6 downto 0);
        dp         : out std_logic;
        an         : out std_logic_vector(3 downto 0);
        -- Pmod JA (t1s_tap Pmod)
        ja1_rx      : in  std_logic;   -- receiver U1 output (low: line negative)
        ja2_trig0   : out std_logic;   -- switch-selected trigger
        ja3_trig1   : out std_logic;   -- beacon
        ja4_trig2   : out std_logic;   -- SSD (packet start)
        ja7_trig3   : out std_logic;   -- any error
        ja8_de      : out std_logic;   -- RS-485 driver enable (kept off)
        ja9_txd     : out std_logic;   -- RS-485 driver data (unused)
        ja10_rxn    : in  std_logic;   -- receiver U2 output (low: line positive)
        -- Pmod JB (Digilent Pmod OLEDrgb)
        jb1_cs      : out std_logic;
        jb2_mosi    : out std_logic;
        jb4_sck     : out std_logic;
        jb7_dc      : out std_logic;
        jb8_res     : out std_logic;
        jb9_vccen   : out std_logic;
        jb10_pmoden : out std_logic
    );
end entity top;

architecture rtl of top is
    -- switch-selectable conditions, index = switch number
    constant N_COND : natural := 12;
    constant N_MODES : natural := 6;        -- seven-segment display modes
    signal cond   : std_logic_vector(N_COND - 1 downto 0);
    signal ev_beacon, ev_commit, ev_ssd, ev_sfd, ev_esd_ok, ev_esd_err,
           ev_esd_jab, ev_burst, ev_crc_err, ev_runt, ev_proto_err, ev_hb,
           ev_node : std_logic;
    signal carrier, in_packet, plca_synced : std_logic;
    signal tx_id : unsigned(7 downto 0);
    signal frame_octets : unsigned(15 downto 0);
    signal sel_id : unsigned(7 downto 0);

    signal any_err  : std_logic;
    signal trig_hit : std_logic;
    signal trig_short, trig_long : std_logic;
    signal led_cond : std_logic_vector(9 downto 0);
    signal led_carrier : std_logic;

    -- buttons: sampled every 1 ms, rising-edge detected
    signal ms_tick  : std_logic := '0';
    signal ms_cnt   : unsigned(16 downto 0) := (others => '0');
    signal btn_s0, btn_s1, btn_q, btn_prev : std_logic_vector(4 downto 0) := (others => '0');
    signal btn_press : std_logic_vector(4 downto 0) := (others => '0');

    -- statistics
    signal sec_tick  : std_logic := '0';
    signal sec_cnt   : unsigned(26 downto 0) := (others => '0');
    signal frames_acc, beacons_acc : unsigned(15 downto 0) := (others => '0');
    signal frames_ps, beacons_ps   : unsigned(15 downto 0) := (others => '0');
    signal crc_errs, proto_errs    : unsigned(15 downto 0) := (others => '0');
    signal mode      : unsigned(2 downto 0) := (others => '0');
    signal oled_ev   : std_logic_vector(N_RATES - 1 downto 0);
    signal disp_val  : std_logic_vector(15 downto 0);
    signal disp_dp   : std_logic_vector(3 downto 0);

    -- timing-jitter SQI+ (one result per transmission)
    signal clk_fast, clk_f90, clk_div, clk_locked : std_logic;
    signal rx_p, rxn_p : std_logic;                   -- receiver pins after the ISERDES pass-through
    signal sqi       : unsigned(4 downto 0);
    signal sqi_valid, var_valid : std_logic;
    signal var_x256  : unsigned(19 downto 0);
    signal sqi_last  : unsigned(4 downto 0) := (others => '0');
    signal sqi_min_acc, sqi_min_1s : unsigned(4 downto 0) := (others => '1');
    signal sqi_var   : unsigned(15 downto 0) := (others => '0');
begin
    u_clk : entity work.clk_gen
        generic map (G_SIM => G_SIM)
        port map (clk_in => clk, clk_fast => clk_fast, clk_f90 => clk_f90, clk_div => clk_div, locked => clk_locked);

    u_sqi : entity work.t1s_sqi
        generic map (G_SIM => G_SIM, FLOOR2_X256 => SQI_FLOOR2_X256)
        port map (clk => clk, clk_fast => clk_fast, clk_f90 => clk_f90, clk_div => clk_div,
                  rx_i => ja1_rx, rxn_i => ja10_rxn, rx_o => rx_p, rxn_o => rxn_p,
                  sqi => sqi, sqi_valid => sqi_valid, var_x256 => var_x256, var_valid => var_valid,
                  edge_dbg => open);

    sel_id <= resize(unsigned(sw(15 downto 12)), 8);

    u_mon : entity work.t1s_monitor
        port map (
            clk => clk, rx_i => rx_p, rxn_i => rxn_p, sel_id => sel_id,
            ev_beacon => ev_beacon, ev_commit => ev_commit, ev_ssd => ev_ssd,
            ev_sfd => ev_sfd, ev_esd_ok => ev_esd_ok, ev_esd_err => ev_esd_err,
            ev_esd_jab => ev_esd_jab, ev_burst => ev_burst, ev_crc_err => ev_crc_err,
            ev_runt => ev_runt, ev_proto_err => ev_proto_err, ev_hb => ev_hb,
            ev_node => ev_node, carrier => carrier, in_packet => in_packet,
            plca_synced => plca_synced, tx_id => tx_id, frame_octets => frame_octets);

    -- ---- trigger conditions ------------------------------------------------
    cond(0)  <= ev_beacon;
    cond(1)  <= ev_commit;
    cond(2)  <= ev_ssd;
    cond(3)  <= ev_sfd;
    cond(4)  <= ev_esd_ok;
    cond(5)  <= ev_esd_err;
    cond(6)  <= ev_esd_jab;
    cond(7)  <= ev_burst;
    cond(8)  <= ev_crc_err;
    cond(9)  <= ev_proto_err or ev_runt;
    cond(10) <= '0';                      -- SW10 selects the pulse width
    cond(11) <= ev_node;

    trig_hit <= '1' when (cond and sw(N_COND - 1 downto 0)) /= (cond'range => '0') else '0';
    any_err  <= ev_esd_err or ev_esd_jab or ev_crc_err or ev_proto_err or ev_runt;

    u_trig_short : entity work.pulse_stretch generic map (LEN => 10)   port map (clk, trig_hit, trig_short);
    u_trig_long  : entity work.pulse_stretch generic map (LEN => 100)  port map (clk, trig_hit, trig_long);
    ja2_trig0 <= trig_long when sw(10) = '1' else trig_short;

    u_trig1 : entity work.pulse_stretch generic map (LEN => 10) port map (clk, ev_beacon, ja3_trig1);
    u_trig2 : entity work.pulse_stretch generic map (LEN => 10) port map (clk, ev_ssd,    ja4_trig2);
    u_trig3 : entity work.pulse_stretch generic map (LEN => 10) port map (clk, any_err,   ja7_trig3);

    ja8_de       <= '0';
    ja9_txd      <= '0';

    -- ---- LEDs ----------------------------------------------------------------
    g_led : for i in 0 to 9 generate
        u_s : entity work.pulse_stretch generic map (LEN => C_CLK_HZ / 20)   -- 50 ms
            port map (clk, cond(i), led_cond(i));
    end generate;
    u_led_car : entity work.pulse_stretch generic map (LEN => C_CLK_HZ / 20)
        port map (clk, carrier, led_carrier);

    led(9 downto 0)   <= led_cond;
    led(10)           <= plca_synced;
    led(11)           <= led_carrier;
    led(15 downto 12) <= std_logic_vector(tx_id(3 downto 0));

    -- ---- buttons -------------------------------------------------------------
    process (clk)
    begin
        if rising_edge(clk) then
            ms_tick <= '0';
            if ms_cnt = C_CLK_HZ / 1000 - 1 then
                ms_cnt  <= (others => '0');
                ms_tick <= '1';
            else
                ms_cnt <= ms_cnt + 1;
            end if;
            btn_s0 <= btnC & btnU & btnD & btnL & btnR;
            btn_s1 <= btn_s0;
            btn_press <= (others => '0');
            if ms_tick = '1' then
                btn_q    <= btn_s1;
                btn_prev <= btn_q;
                btn_press <= btn_q and not btn_prev;
            end if;
        end if;
    end process;

    -- ---- statistics and display ------------------------------------------------
    process (clk)
    begin
        if rising_edge(clk) then
            sec_tick <= '0';
            if sec_cnt = C_CLK_HZ - 1 then
                sec_cnt  <= (others => '0');
                sec_tick <= '1';
            else
                sec_cnt <= sec_cnt + 1;
            end if;

            if sec_tick = '1' then
                frames_ps  <= frames_acc;
                beacons_ps <= beacons_acc;
                frames_acc  <= (others => '0');
                beacons_acc <= (others => '0');
            else
                if ev_esd_ok = '1' and frames_acc /= 65535 then
                    frames_acc <= frames_acc + 1;
                end if;
                if ev_beacon = '1' and beacons_acc /= 65535 then
                    beacons_acc <= beacons_acc + 1;
                end if;
            end if;

            if btn_press(4) = '1' then          -- btnC: reset counters
                crc_errs   <= (others => '0');
                proto_errs <= (others => '0');
            else
                if ev_crc_err = '1' and crc_errs /= 65535 then
                    crc_errs <= crc_errs + 1;
                end if;
                if (ev_proto_err = '1' or ev_runt = '1') and proto_errs /= 65535 then
                    proto_errs <= proto_errs + 1;
                end if;
            end if;

            if btn_press(3) = '1' then          -- btnU
                if mode = N_MODES - 1 then mode <= (others => '0'); else mode <= mode + 1; end if;
            elsif btn_press(2) = '1' then       -- btnD
                if mode = 0 then mode <= to_unsigned(N_MODES - 1, 3); else mode <= mode - 1; end if;
            end if;

            -- SQI+: last transmission, and the worst of the last second
            if sqi_valid = '1' then
                sqi_last <= sqi;
                if sqi < sqi_min_acc then
                    sqi_min_acc <= sqi;
                end if;
            end if;
            if var_valid = '1' then
                sqi_var <= var_x256(15 downto 0);
            end if;
            if sec_tick = '1' then
                sqi_min_1s  <= sqi_min_acc;
                sqi_min_acc <= (others => '1');
            end if;
        end if;
    end process;

    with mode select disp_val <=
        std_logic_vector(frames_ps)  when "000",  -- good frames per second
        std_logic_vector(beacons_ps) when "001",  -- beacons per second
        std_logic_vector(crc_errs)   when "010",  -- CRC errors since reset
        std_logic_vector(proto_errs) when "011",  -- protocol errors since reset
        "000" & std_logic_vector(sqi_min_1s) & "000" & std_logic_vector(sqi_last) when "100",  -- SQI+ worst/1 s, last
        std_logic_vector(sqi_var)    when others; -- jitter variance S*256/N of the last transmission, hex
    disp_dp <= "0001" when mode = 0 else
               "0010" when mode = 1 else
               "0100" when mode = 2 else
               "1000" when mode = 3 else
               "0011" when mode = 4 else
               "1100";

    u_seg : entity work.seg7
        port map (clk => clk, value => disp_val, dp => disp_dp, seg => seg, dp_o => dp, an => an);

    -- ---- OLED status screen (Pmod JB) -------------------------------------------
    oled_ev <= ev_hb & any_err & trig_hit & cond(11) & cond(9 downto 0);

    u_oled : entity work.oled_status
        generic map (CLKS_PER_MS => OLED_CLKS_PER_MS, SPI_DIV => OLED_SPI_DIV)
        port map (clk => clk, sec_tick => sec_tick, sw => sw, plca_synced => plca_synced,
                  events => oled_ev, sqi_last => sqi_last, sqi_min => sqi_min_1s, frame => open,
                  cs_n => jb1_cs, mosi => jb2_mosi, sck => jb4_sck, dc => jb7_dc,
                  res_n => jb8_res, vccen => jb9_vccen, pmoden => jb10_pmoden);
end architecture rtl;
