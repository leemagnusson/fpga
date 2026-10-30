-- The board-independent core: line in, event pulses and status out.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.t1s_pkg.all;

entity t1s_monitor is
    port (
        clk          : in  std_logic;
        rx_i         : in  std_logic;             -- line level from the Pmod receiver
        sel_id       : in  unsigned(7 downto 0);  -- node ID for ev_node
        -- events (one clock each)
        ev_beacon    : out std_logic;
        ev_commit    : out std_logic;
        ev_ssd       : out std_logic;
        ev_sfd       : out std_logic;
        ev_esd_ok    : out std_logic;
        ev_esd_err   : out std_logic;
        ev_esd_jab   : out std_logic;
        ev_burst     : out std_logic;
        ev_crc_err   : out std_logic;
        ev_runt      : out std_logic;
        ev_proto_err : out std_logic;
        ev_hb        : out std_logic;
        ev_node      : out std_logic;             -- SSD of a packet sent by node sel_id
        -- status
        carrier      : out std_logic;             -- level: transitions on the line
        in_packet    : out std_logic;
        plca_synced  : out std_logic;
        tx_id        : out unsigned(7 downto 0);
        frame_octets : out unsigned(15 downto 0)
    );
end entity t1s_monitor;

architecture rtl of t1s_monitor is
    signal bit_valid, bit_val, start, silent, violation : std_logic;
    signal in_beacon, beacon_end : std_logic;
    signal ssd_i : std_logic;
    signal txid  : unsigned(7 downto 0);
    signal cur_id : unsigned(7 downto 0);
begin
    u_dme : entity work.dme_rx
        port map (
            clk => clk, rx_i => rx_i,
            bit_valid => bit_valid, bit_val => bit_val,
            start => start, silent => silent, violation => violation);

    u_pcs : entity work.t1s_pcs_rx
        port map (
            clk => clk,
            bit_valid => bit_valid, bit_val => bit_val,
            start => start, silent => silent, violation => violation,
            ev_beacon => ev_beacon, ev_commit => ev_commit, ev_ssd => ssd_i,
            ev_sfd => ev_sfd, ev_esd_ok => ev_esd_ok, ev_esd_err => ev_esd_err,
            ev_esd_jab => ev_esd_jab, ev_burst => ev_burst, ev_crc_err => ev_crc_err,
            ev_runt => ev_runt, ev_proto_err => ev_proto_err, ev_hb => ev_hb,
            in_beacon => in_beacon, beacon_end => beacon_end,
            in_packet => in_packet, frame_octets => frame_octets);

    u_plca : entity work.plca_track
        port map (
            clk => clk, silent => silent, start => start,
            in_beacon => in_beacon, beacon_end => beacon_end,
            tx_id => txid, cur_id => cur_id, plca_synced => plca_synced);

    ev_ssd  <= ssd_i;
    ev_node <= ssd_i when txid = sel_id else '0';
    carrier <= not silent;
    tx_id   <= txid;
end architecture rtl;
