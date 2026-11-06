-- Follows the PLCA (IEEE 802.3 Clause 148) cycle from what is visible on the
-- wire, to attribute each transmission to a node ID.
--
-- After the coordinator's BEACON the transmit opportunities (TO) go round in
-- node ID order. A TO is ceded by staying silent for to_timer (32 bit times
-- by default); a node that transmits uses the current TO and the count moves
-- on when its transmission ends. So: reset the ID at the end of the beacon,
-- count up at every to_timer of silence and after every transmission, and the
-- ID at the moment a transmission starts is the sender.
--
-- Limits: a node that pauses within a burst for longer than SILENCE (160 ns)
-- is counted as the next ID; a network without PLCA (CSMA/CD) never syncs and
-- tx_id is meaningless there (plca_synced = '0').

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.t1s_pkg.all;

entity plca_track is
    generic (
        TO_CLKS : natural := C_PLCA_TO_CLKS
    );
    port (
        clk         : in  std_logic;
        silent      : in  std_logic;   -- from dme_rx
        start       : in  std_logic;   -- first edge of a transmission
        in_beacon   : in  std_logic;
        beacon_end  : in  std_logic;
        tx_id       : out unsigned(7 downto 0);  -- node ID of the current / last transmission
        cur_id      : out unsigned(7 downto 0);  -- ID whose transmit opportunity it is now
        plca_synced : out std_logic              -- a beacon was seen in the last ~100 ms
    );
end entity plca_track;

architecture rtl of plca_track is
    constant SYNC_TIMEOUT : natural := C_CLK_HZ / 10;   -- 100 ms

    signal id        : unsigned(7 downto 0) := (others => '0');
    signal txid      : unsigned(7 downto 0) := (others => '0');
    signal to_cnt    : unsigned(15 downto 0) := (others => '0');
    signal counting  : std_logic := '0';
    signal silent_d  : std_logic := '1';
    signal was_beacon : std_logic := '0';
    signal sync_cnt  : unsigned(26 downto 0) := (others => '0');
    signal synced    : std_logic := '0';
begin
    tx_id       <= txid;
    cur_id      <= id;
    plca_synced <= synced;

    process (clk)
    begin
        if rising_edge(clk) then
            silent_d <= silent;

            if in_beacon = '1' then
                was_beacon <= '1';
            end if;

            if beacon_end = '1' then
                id         <= (others => '0');
                to_cnt     <= (others => '0');
                counting   <= '1';
                was_beacon <= '0';
                sync_cnt   <= (others => '0');
                synced     <= '1';
            elsif start = '1' then
                txid     <= id;
                counting <= '0';
            elsif silent = '1' and silent_d = '0' then
                -- a transmission ended (a beacon's end is handled above)
                if was_beacon = '0' and id /= 255 then
                    id <= id + 1;
                end if;
                was_beacon <= '0';
                to_cnt     <= (others => '0');
                counting   <= '1';
            elsif counting = '1' and silent = '1' then
                if to_cnt = TO_CLKS - 1 then
                    to_cnt <= (others => '0');
                    if id /= 255 then
                        id <= id + 1;
                    end if;
                else
                    to_cnt <= to_cnt + 1;
                end if;
            end if;

            if beacon_end = '0' then
                if sync_cnt = SYNC_TIMEOUT then
                    synced <= '0';
                else
                    sync_cnt <= sync_cnt + 1;
                end if;
            end if;
        end if;
    end process;
end architecture rtl;
