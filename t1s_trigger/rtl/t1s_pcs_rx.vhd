-- 10BASE-T1S PCS receive: groups recovered bits into 5B symbols, follows the
-- transmission structure (BEACON, COMMIT, SYNC/SSD, scrambled preamble, SFD,
-- data, ESD) and reports each thing it sees as a one-clock event pulse.
--
-- Symbol alignment comes from the first edge after SILENCE (dme_rx.start):
-- every transmission starts on a symbol boundary. Within a packet the 4B data
-- is descrambled (x^17 + x^14 + 1, self-synchronising) and the FCS checked.
--
-- Events (all single-clock pulses):
--   ev_beacon    first N symbol of a BEACON
--   ev_commit    third consecutive J symbol (a packet alone has only two)
--   ev_ssd       second SSD symbol: start of a packet on the wire
--   ev_sfd       SFD found in the descrambled preamble (first data nibble follows)
--   ev_esd_ok    T R (or R R at the end of a burst packet)
--   ev_esd_err   T K, transmitter signalled an error
--   ev_esd_jab   T S, jabber (see C_SYM_S in t1s_pkg)
--   ev_burst     R R: packet ended, the same node continues without ceding
--   ev_crc_err   packet ended with ESDOK but its FCS is wrong (or had an odd
--                number of nibbles)
--   ev_runt      packet ended with ESDOK but is shorter than 64 octets
--   ev_proto_err anything the coding rules do not allow: invalid 5B code,
--                symbol out of place, DME timing violation, transmission cut
--                off by silence, no SFD within the preamble, ESD not followed
--                by a delimiter
--   ev_hb        a run of T symbols from silence (heartbeat / SUSPEND signalling)

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.t1s_pkg.all;

entity t1s_pcs_rx is
    port (
        clk          : in  std_logic;
        -- from dme_rx
        bit_valid    : in  std_logic;
        bit_val      : in  std_logic;
        start        : in  std_logic;
        silent       : in  std_logic;
        violation    : in  std_logic;
        -- events
        ev_beacon    : out std_logic := '0';
        ev_commit    : out std_logic := '0';
        ev_ssd       : out std_logic := '0';
        ev_sfd       : out std_logic := '0';
        ev_esd_ok    : out std_logic := '0';
        ev_esd_err   : out std_logic := '0';
        ev_esd_jab   : out std_logic := '0';
        ev_burst     : out std_logic := '0';
        ev_crc_err   : out std_logic := '0';
        ev_runt      : out std_logic := '0';
        ev_proto_err : out std_logic := '0';
        ev_hb        : out std_logic := '0';
        -- status
        in_beacon    : out std_logic := '0';   -- level: inside a BEACON
        beacon_end   : out std_logic := '0';   -- pulse: silence after a BEACON
        in_packet    : out std_logic := '0';   -- level: SSD seen, ESD not yet
        frame_octets : out unsigned(15 downto 0)  -- octets of the last packet (after SFD, incl. FCS)
    );
end entity t1s_pcs_rx;

architecture rtl of t1s_pcs_rx is
    type t_state is (ST_IDLE, ST_BEACON, ST_SYNC, ST_SSD1, ST_PRE, ST_SFD,
                     ST_DATA, ST_ESD, ST_BURST, ST_HB, ST_JUNK);
    signal state : t_state := ST_IDLE;

    signal sym_sr    : std_logic_vector(4 downto 0) := (others => '0');
    signal bit_cnt   : unsigned(2 downto 0) := (others => '0');
    signal silent_d  : std_logic := '1';

    signal j_cnt     : unsigned(1 downto 0) := (others => '0');
    signal pre_cnt   : unsigned(3 downto 0) := (others => '0');
    signal sfd_cnt   : unsigned(3 downto 0) := (others => '0');
    signal dcr       : std_logic_vector(16 downto 0) := (others => '0');
    signal nib_hi    : std_logic := '0';   -- '1': next nibble completes an octet
    signal octets    : unsigned(15 downto 0) := (others => '0');
    signal crc       : std_logic_vector(31 downto 0) := C_CRC32_INIT;
    signal burst     : std_logic := '0';
begin
    in_beacon    <= '1' when state = ST_BEACON else '0';
    in_packet    <= '1' when state = ST_PRE or state = ST_SFD or state = ST_DATA or state = ST_ESD else '0';
    frame_octets <= octets;

    process (clk)
        variable sym       : std_logic_vector(4 downto 0);
        variable sym_valid : boolean;
        variable kind      : t_sym_kind;
        variable nib       : std_logic_vector(3 downto 0);
        variable dnib      : std_logic_vector(3 downto 0);   -- descrambled
        variable d         : std_logic_vector(16 downto 0);
        variable fail      : boolean;
    begin
        if rising_edge(clk) then
            ev_beacon    <= '0';
            ev_commit    <= '0';
            ev_ssd       <= '0';
            ev_sfd       <= '0';
            ev_esd_ok    <= '0';
            ev_esd_err   <= '0';
            ev_esd_jab   <= '0';
            ev_burst     <= '0';
            ev_crc_err   <= '0';
            ev_runt      <= '0';
            ev_proto_err <= '0';
            ev_hb        <= '0';
            beacon_end   <= '0';
            silent_d     <= silent;

            -- ---- 5B symbol assembly, LSB first, aligned to the first edge --
            sym_valid := false;
            sym       := sym_sr;
            if start = '1' then
                bit_cnt <= (others => '0');
            elsif bit_valid = '1' then
                sym(to_integer(bit_cnt)) := bit_val;
                sym_sr <= sym;
                if bit_cnt = 4 then
                    bit_cnt   <= (others => '0');
                    sym_valid := true;
                else
                    bit_cnt <= bit_cnt + 1;
                end if;
            end if;
            decode_5b(sym, kind, nib);

            -- descramble the nibble (only used in the packet states)
            d := dcr;
            for i in 0 to 3 loop
                dnib(i) := nib(i) xor d(13) xor d(16);
                d := d(15 downto 0) & nib(i);
            end loop;

            fail := false;

            -- ---- line went silent: close whatever was in progress ---------
            if silent = '1' and silent_d = '0' then
                case state is
                    when ST_IDLE | ST_SYNC | ST_JUNK | ST_BURST => null;
                    when ST_BEACON => beacon_end <= '1';
                    when ST_HB     => ev_hb <= '1';
                    when others    => ev_proto_err <= '1';   -- cut off mid-packet
                end case;
                state <= ST_IDLE;

            elsif violation = '1' and state /= ST_IDLE and state /= ST_BEACON
                                  and state /= ST_HB and state /= ST_JUNK then
                fail := true;

            elsif sym_valid then
                case state is
                    when ST_IDLE =>
                        case kind is
                            when SK_J => state <= ST_SYNC; j_cnt <= to_unsigned(1, 2);
                            when SK_N => state <= ST_BEACON; ev_beacon <= '1';
                            when SK_T => state <= ST_HB;
                            when others => fail := true;
                        end case;

                    when ST_BEACON =>
                        if kind /= SK_N then
                            ev_proto_err <= '1';     -- stay: beacon ends at silence
                        end if;

                    when ST_SYNC =>
                        case kind is
                            when SK_J =>
                                if j_cnt = 2 then
                                    ev_commit <= '1';
                                end if;
                                if j_cnt /= 3 then
                                    j_cnt <= j_cnt + 1;
                                end if;
                            when SK_H => state <= ST_SSD1;
                            when others => fail := true;
                        end case;

                    when ST_SSD1 =>
                        if kind = SK_H then
                            state   <= ST_PRE;
                            ev_ssd  <= '1';
                            pre_cnt <= (others => '0');
                            sfd_cnt <= (others => '0');
                            dcr     <= (others => '0');
                            nib_hi  <= '0';
                            octets  <= (others => '0');
                            crc     <= C_CRC32_INIT;
                            burst   <= '0';
                        else
                            fail := true;
                        end if;

                    when ST_PRE =>
                        -- nine symbols are discarded while the descrambler locks
                        if kind = SK_DATA then
                            dcr <= d;
                            if pre_cnt = 8 then
                                state <= ST_SFD;
                            else
                                pre_cnt <= pre_cnt + 1;
                            end if;
                        else
                            fail := true;
                        end if;

                    when ST_SFD =>
                        if kind = SK_DATA then
                            dcr <= d;
                            if dnib = x"D" then
                                state  <= ST_DATA;
                                ev_sfd <= '1';
                            elsif dnib = x"5" and sfd_cnt /= 15 then
                                sfd_cnt <= sfd_cnt + 1;
                            else
                                fail := true;                  -- no SFD
                            end if;
                        else
                            fail := true;
                        end if;

                    when ST_DATA =>
                        case kind is
                            when SK_DATA =>
                                dcr    <= d;
                                crc    <= crc32_update(crc, dnib);
                                nib_hi <= not nib_hi;
                                if nib_hi = '1' and octets /= 65535 then
                                    octets <= octets + 1;
                                end if;
                            when SK_T => state <= ST_ESD; burst <= '0';
                            when SK_R => state <= ST_ESD; burst <= '1';   -- ESDBRS
                            when others => fail := true;
                        end case;

                    when ST_ESD =>
                        case kind is
                            when SK_R =>
                                ev_esd_ok <= '1';
                                if crc /= C_CRC32_RESIDUE or nib_hi = '1' then
                                    ev_crc_err <= '1';
                                end if;
                                if octets < 64 then
                                    ev_runt <= '1';
                                end if;
                                if burst = '1' then
                                    ev_burst <= '1';
                                    state    <= ST_BURST;
                                else
                                    state <= ST_JUNK;
                                end if;
                            when SK_K => ev_esd_err <= '1'; state <= ST_JUNK;
                            when SK_S => ev_esd_jab <= '1'; state <= ST_JUNK;
                            when others => fail := true;
                        end case;

                    when ST_BURST =>
                        -- the same node carries on: J (commit/sync) then H H
                        case kind is
                            when SK_J => state <= ST_SYNC; j_cnt <= to_unsigned(1, 2);
                            when others => fail := true;
                        end case;

                    when ST_HB =>
                        if kind /= SK_T then
                            fail := true;
                        end if;

                    when ST_JUNK => null;   -- wait for silence
                end case;
            end if;

            if fail then
                ev_proto_err <= '1';
                state        <= ST_JUNK;
            end if;
        end if;
    end process;
end architecture rtl;
