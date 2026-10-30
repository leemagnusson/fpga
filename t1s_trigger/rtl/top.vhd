-- Basys 3 top level: 10BASE-T1S line monitor with switch-selected trigger
-- outputs. See README.md for the switch, LED and Pmod assignments.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.t1s_pkg.all;

entity top is
    port (
        clk        : in  std_logic;                      -- 100 MHz
        sw         : in  std_logic_vector(15 downto 0);
        led        : out std_logic_vector(15 downto 0);
        btnC, btnU, btnD, btnL, btnR : in std_logic;
        seg        : out std_logic_vector(6 downto 0);
        dp         : out std_logic;
        an         : out std_logic_vector(3 downto 0);
        -- Pmod JA (t1s_tap Pmod)
        ja1_rx      : in  std_logic;   -- receiver output (line level)
        ja2_trig0   : out std_logic;   -- switch-selected trigger
        ja3_trig1   : out std_logic;   -- beacon
        ja4_trig2   : out std_logic;   -- SSD (packet start)
        ja7_trig3   : out std_logic;   -- any error
        ja8_de      : out std_logic;   -- RS-485 driver enable (kept off)
        ja9_txd     : out std_logic;   -- RS-485 driver data (unused)
        ja10_carrier : out std_logic   -- line active (not silent)
    );
end entity top;

architecture rtl of top is
    -- switch-selectable conditions, index = switch number
    constant N_COND : natural := 12;
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
    signal mode      : unsigned(1 downto 0) := (others => '0');
    signal disp_val  : std_logic_vector(15 downto 0);
    signal disp_dp   : std_logic_vector(3 downto 0);
begin
    sel_id <= resize(unsigned(sw(15 downto 12)), 8);

    u_mon : entity work.t1s_monitor
        port map (
            clk => clk, rx_i => ja1_rx, sel_id => sel_id,
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
    ja10_carrier <= carrier;

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
                mode <= mode + 1;
            elsif btn_press(2) = '1' then       -- btnD
                mode <= mode - 1;
            end if;
        end if;
    end process;

    with mode select disp_val <=
        std_logic_vector(frames_ps)  when "00",   -- good frames per second
        std_logic_vector(beacons_ps) when "01",   -- beacons per second
        std_logic_vector(crc_errs)   when "10",   -- CRC errors since reset
        std_logic_vector(proto_errs) when others; -- protocol errors since reset
    disp_dp <= "0001" when mode = 0 else
               "0010" when mode = 1 else
               "0100" when mode = 2 else
               "1000";

    u_seg : entity work.seg7
        port map (clk => clk, value => disp_val, dp => disp_dp, seg => seg, dp_o => dp, an => an);
end architecture rtl;
