-- Self-checking testbench for the 10BASE-T1S trigger monitor.
--
-- A behavioural 10BASE-T1S transmitter (DME at 12.5 MBd, 4B/5B, the x^17+x^14+1
-- scrambler, Ethernet FCS) drives the line into both the board-independent
-- core (to count its event pulses) and the Basys 3 top level (to check the
-- switch gating and the trigger pulse widths). Run with:
--
--   ghdl -a --std=08 rtl/*.vhd sim/tb_top.vhd && ghdl --elab-run --std=08 tb_top
--
-- It prints "TB PASSED" and stops, or fails an assertion.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.t1s_pkg.all;

entity tb_top is
end entity tb_top;

architecture sim of tb_top is
    constant HALF : time := 40 ns;     -- half a 12.5 MBd bit cell

    signal clk  : std_logic := '0';
    signal line : std_logic := '1';    -- receiver output idles high (fail-safe)
    signal done : boolean := false;

    -- core under test
    signal sel_id : unsigned(7 downto 0) := to_unsigned(3, 8);
    signal ev_beacon, ev_commit, ev_ssd, ev_sfd, ev_esd_ok, ev_esd_err,
           ev_esd_jab, ev_burst, ev_crc_err, ev_runt, ev_proto_err, ev_hb,
           ev_node, carrier, in_packet, plca_synced : std_logic;
    signal tx_id : unsigned(7 downto 0);
    signal frame_octets : unsigned(15 downto 0);

    -- event counters
    signal n_beacon, n_commit, n_ssd, n_sfd, n_esd_ok, n_esd_err, n_esd_jab,
           n_burst, n_crc_err, n_runt, n_proto_err, n_hb, n_node : natural := 0;
    signal id_at_ssd : integer := -1;

    -- top level under test
    signal sw  : std_logic_vector(15 downto 0) := (others => '0');
    signal led : std_logic_vector(15 downto 0);
    signal seg : std_logic_vector(6 downto 0);
    signal dp  : std_logic;
    signal an  : std_logic_vector(3 downto 0);
    signal trig0, trig1, trig2, trig3, de, txd, car : std_logic;
    signal n_trig0 : natural := 0;
    signal trig0_width : time := 0 ns;
    signal trig0_rise  : time := 0 ns;

    signal errors : natural := 0;

    type t_bytes is array (natural range <>) of std_logic_vector(7 downto 0);
    type t_end is (END_OK, END_ERR, END_JAB, END_BURST);

    function b2i(b : std_logic) return integer is
    begin
        if b = '1' then return 1; else return 0; end if;
    end function;
begin
    clk <= not clk after 5 ns when not done else '0';

    dut_core : entity work.t1s_monitor
        port map (
            clk => clk, rx_i => line, sel_id => sel_id,
            ev_beacon => ev_beacon, ev_commit => ev_commit, ev_ssd => ev_ssd,
            ev_sfd => ev_sfd, ev_esd_ok => ev_esd_ok, ev_esd_err => ev_esd_err,
            ev_esd_jab => ev_esd_jab, ev_burst => ev_burst, ev_crc_err => ev_crc_err,
            ev_runt => ev_runt, ev_proto_err => ev_proto_err, ev_hb => ev_hb,
            ev_node => ev_node, carrier => carrier, in_packet => in_packet,
            plca_synced => plca_synced, tx_id => tx_id, frame_octets => frame_octets);

    dut_top : entity work.top
        port map (
            clk => clk, sw => sw, led => led,
            btnC => '0', btnU => '0', btnD => '0', btnL => '0', btnR => '0',
            seg => seg, dp => dp, an => an,
            ja1_rx => line, ja2_trig0 => trig0, ja3_trig1 => trig1,
            ja4_trig2 => trig2, ja7_trig3 => trig3, ja8_de => de, ja9_txd => txd,
            ja10_carrier => car);

    -- count every event pulse
    process (clk)
    begin
        if rising_edge(clk) then
            if ev_beacon = '1'    then n_beacon    <= n_beacon + 1;    end if;
            if ev_commit = '1'    then n_commit    <= n_commit + 1;    end if;
            if ev_ssd = '1'       then n_ssd       <= n_ssd + 1; id_at_ssd <= to_integer(tx_id); end if;
            if ev_sfd = '1'       then n_sfd       <= n_sfd + 1;       end if;
            if ev_esd_ok = '1'    then n_esd_ok    <= n_esd_ok + 1;    end if;
            if ev_esd_err = '1'   then n_esd_err   <= n_esd_err + 1;   end if;
            if ev_esd_jab = '1'   then n_esd_jab   <= n_esd_jab + 1;   end if;
            if ev_burst = '1'     then n_burst     <= n_burst + 1;     end if;
            if ev_crc_err = '1'   then n_crc_err   <= n_crc_err + 1;   end if;
            if ev_runt = '1'      then n_runt      <= n_runt + 1;      end if;
            if ev_proto_err = '1' then n_proto_err <= n_proto_err + 1; end if;
            if ev_hb = '1'        then n_hb        <= n_hb + 1;        end if;
            if ev_node = '1'      then n_node      <= n_node + 1;      end if;
        end if;
    end process;

    -- trigger 0: count pulses and measure the last width
    process (trig0)
    begin
        if rising_edge(trig0) then
            n_trig0    <= n_trig0 + 1;
            trig0_rise <= now;
        elsif falling_edge(trig0) then
            trig0_width <= now - trig0_rise;
        end if;
    end process;

    stimulus : process
        variable scr : std_logic_vector(16 downto 0) := "10101100111000101";

        procedure check(name : string; actual, expected : integer) is
        begin
            if actual /= expected then
                report "CHECK FAILED: " & name & " = " & integer'image(actual) &
                       ", expected " & integer'image(expected) severity error;
                errors <= errors + 1;
                wait for 0 ns;
            end if;
        end procedure;

        procedure check_time(name : string; actual, lo, hi : time) is
        begin
            if actual < lo or actual > hi then
                report "CHECK FAILED: " & name & " = " & time'image(actual) &
                       ", expected " & time'image(lo) & " .. " & time'image(hi) severity error;
                errors <= errors + 1;
                wait for 0 ns;
            end if;
        end procedure;

        -- DME: clock transition at the start of each bit, data transition
        -- mid-bit for a 1. 5B symbols go LSB first.
        procedure send_sym(s : std_logic_vector(4 downto 0)) is
        begin
            for i in 0 to 4 loop
                line <= not line;
                wait for HALF;
                if s(i) = '1' then
                    line <= not line;
                end if;
                wait for HALF;
            end loop;
        end procedure;

        procedure send_raw_bits(b : std_logic_vector) is   -- b(0) first
        begin
            for i in b'low to b'high loop
                line <= not line;
                wait for HALF;
                if b(i) = '1' then
                    line <= not line;
                end if;
                wait for HALF;
            end loop;
        end procedure;

        -- multiplicative scrambler x^17 + x^14 + 1 on the 4B bits, LSB first
        procedure send_nibble(n : std_logic_vector(3 downto 0)) is
            variable sd : std_logic_vector(3 downto 0);
        begin
            for i in 0 to 3 loop
                sd(i) := n(i) xor scr(13) xor scr(16);
                scr   := scr(15 downto 0) & sd(i);
            end loop;
            send_sym(encode_4b(sd));
        end procedure;

        procedure send_byte(b : std_logic_vector(7 downto 0)) is
        begin
            send_nibble(b(3 downto 0));
            send_nibble(b(7 downto 4));
        end procedure;

        procedure silence(t : time) is
        begin
            wait for t;
        end procedure;

        procedure beacon(n : natural := 5) is
        begin
            for i in 1 to n loop send_sym(C_SYM_N); end loop;
        end procedure;

        procedure commit(n : natural) is
        begin
            for i in 1 to n loop send_sym(C_SYM_J); end loop;
        end procedure;

        -- SYNC SYNC SSD SSD, scrambled preamble remainder and SFD
        procedure packet_start is
        begin
            send_sym(C_SYM_J); send_sym(C_SYM_J);
            send_sym(C_SYM_H); send_sym(C_SYM_H);
            for i in 1 to 11 loop send_nibble(x"5"); end loop;
            send_nibble(x"D");
        end procedure;

        procedure packet_end(e : t_end) is
        begin
            case e is
                when END_OK    => send_sym(C_SYM_T); send_sym(C_SYM_R);
                when END_ERR   => send_sym(C_SYM_T); send_sym(C_SYM_K);
                when END_JAB   => send_sym(C_SYM_T); send_sym(C_SYM_S);
                when END_BURST => send_sym(C_SYM_R); send_sym(C_SYM_R);
            end case;
        end procedure;

        -- payload = everything after the SFD, FCS is appended here
        procedure packet(payload : t_bytes; e : t_end := END_OK; bad_fcs : boolean := false) is
            variable crc : std_logic_vector(31 downto 0) := C_CRC32_INIT;
            variable fcs : std_logic_vector(31 downto 0);
        begin
            packet_start;
            for i in payload'range loop
                send_byte(payload(i));
                crc := crc32_update(crc, payload(i)(3 downto 0));
                crc := crc32_update(crc, payload(i)(7 downto 4));
            end loop;
            fcs := not crc;
            if bad_fcs then
                fcs(5) := not fcs(5);
            end if;
            send_byte(fcs(7 downto 0));
            send_byte(fcs(15 downto 8));
            send_byte(fcs(23 downto 16));
            send_byte(fcs(31 downto 24));
            packet_end(e);
        end procedure;

        function test_payload(n : natural; seed : natural) return t_bytes is
            variable p : t_bytes(0 to n - 1);
        begin
            for i in 0 to n - 1 loop
                p(i) := std_logic_vector(to_unsigned((i * 7 + seed * 13) mod 256, 8));
            end loop;
            return p;
        end function;

        constant P60 : t_bytes(0 to 59) := test_payload(60, 1);   -- 64-octet frame with FCS
        constant P16 : t_bytes(0 to 15) := test_payload(16, 2);   -- runt
    begin
        -- trigger 0 armed on CRC errors only; node filter set to ID 3
        sw <= (8 => '1', 15 downto 12 => "0011", others => '0');
        silence(2 us);

        -- 1. beacon
        beacon(5);
        silence(1 us);
        check("beacon", n_beacon, 1);
        check("plca_synced", b2i(plca_synced), 1);

        -- 2. node 0 and node 1 cede their TOs (32 BT each), node 2 sends
        silence(5.7 us);          -- 6.7 us since beacon end
        packet(P60);
        silence(1 us);
        check("ssd after good frame", n_ssd, 1);
        check("sfd", n_sfd, 1);
        check("esd_ok", n_esd_ok, 1);
        check("crc_err (good frame)", n_crc_err, 0);
        check("runt (good frame)", n_runt, 0);
        check("proto_err (good frame)", n_proto_err, 0);
        check("tx_id of node 2", id_at_ssd, 2);
        check("frame_octets", to_integer(frame_octets), 64);

        -- 3. node 3 commits first, then sends (ev_node must fire)
        commit(8);
        packet(P60);
        silence(1 us);
        check("commit", n_commit, 1);
        check("ssd", n_ssd, 2);
        check("tx_id of node 3", id_at_ssd, 3);
        check("node match", n_node, 1);

        -- 4. node 4: bad FCS -> trigger 0 fires once, 100 ns wide
        packet(P60, END_OK, true);
        silence(1 us);
        check("crc_err", n_crc_err, 1);
        check("esd_ok incl. bad fcs", n_esd_ok, 3);
        check("trig0 pulses", n_trig0, 1);
        check_time("trig0 width (sw10=0)", trig0_width, 90 ns, 120 ns);

        -- 5. transmitter-signalled error
        packet(P60, END_ERR);
        silence(1 us);
        check("esd_err", n_esd_err, 1);
        check("crc_err unchanged", n_crc_err, 1);

        -- 6. burst: two packets back to back from one node
        packet(P60, END_BURST);
        packet(P60, END_OK);
        silence(1 us);
        check("burst", n_burst, 1);
        check("esd_ok after burst", n_esd_ok, 5);
        check("ssd after burst", n_ssd, 6);

        -- 7. runt
        packet(P16);
        silence(1 us);
        check("runt", n_runt, 1);
        check("esd_ok after runt", n_esd_ok, 6);

        -- 8. invalid 5B code inside the data
        packet_start;
        send_byte(x"AA"); send_byte(x"55");
        send_sym("00000");
        send_byte(x"AA");
        silence(1 us);
        check("proto_err (invalid symbol)", n_proto_err, 1);

        -- 9. transmission cut off mid packet
        packet_start;
        send_byte(x"12"); send_byte(x"34"); send_byte(x"56");
        silence(1 us);
        check("proto_err (truncated)", n_proto_err, 2);

        -- 10. jabber
        packet(P60, END_JAB);
        silence(1 us);
        check("esd_jab", n_esd_jab, 1);

        -- 11. heartbeat / suspend: a run of T
        send_sym(C_SYM_T); send_sym(C_SYM_T); send_sym(C_SYM_T);
        silence(1 us);
        check("hb", n_hb, 1);
        check("proto_err unchanged by hb", n_proto_err, 2);

        -- 12. next cycle: beacon, node 0 sends at once; trigger 0 now on
        --     beacons with the 1 us pulse width
        sw <= (0 => '1', 10 => '1', 15 downto 12 => "0011", others => '0');
        silence(1 us);
        beacon(5);
        silence(600 ns);
        packet(P60);
        silence(1.5 us);
        check("beacon #2", n_beacon, 2);
        check("tx_id of node 0", id_at_ssd, 0);
        check("trig0 pulses (beacon)", n_trig0, 2);
        check_time("trig0 width (sw10=1)", trig0_width, 990 ns, 1020 ns);
        check("node match unchanged", n_node, 1);
        check("sfd total", n_sfd, 11);
        check("led node id", to_integer(unsigned(led(15 downto 12))), 0);

        -- 13. a DME timing violation inside a packet
        packet_start;
        send_byte(x"01");
        line <= not line; wait for HALF;      -- half cell ...
        line <= not line; wait for 2 * HALF;  -- ... then a full cell from mid-cell
        send_byte(x"02");
        silence(1 us);
        check("proto_err (dme violation)", n_proto_err, 3);

        wait for 100 ns;
        if errors = 0 then
            report "TB PASSED";
        else
            report integer'image(errors) & " checks failed" severity failure;
        end if;
        done <= true;
        wait;
    end process;
end architecture sim;
