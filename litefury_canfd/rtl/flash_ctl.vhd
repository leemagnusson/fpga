-- Configuration flash access, reboot trigger and image ID for misc_regs.
--
-- * SPI master (mode 0, MSB first, clk/8 = 10 MHz at 80 MHz) on the FPGA's
--   configuration flash pins. CCLK is a dedicated pin and is driven through
--   STARTUPE2; note that STARTUPE2 swallows the first three clock cycles
--   after configuration (UG470, USRCCLKO), so the host sends a dummy byte
--   with the chip deselected first.
--   A transfer shifts the top NBYTES bytes of TX out and the same number of
--   bytes into the low end of RX. It starts when GO differs from its last
--   written value, so that a repeated bus write is harmless.
-- * Reboot: writes the IPROG sequence of UG470 table 7-1 to ICAPE2 with the
--   given warm boot address, which reconfigures the FPGA from that flash
--   address (0 = the normal power-up path).
-- * image_id: the bitstream's USR_ACCESS word (BITSTREAM.CONFIG.USR_ACCESS),
--   which tells the host which image is running.
-- * On-chip monitor (XADC in its default mode: die temperature and the
--   VCCINT/VCCAUX supplies): the three status registers are read over the DRP,
--   each about 400 times a second, and handed out raw (12-bit code in bits 15:4;
--   UG480: temperature = code * 503.975 / 4096 - 273.15 C, supply = code * 3 V / 4096).

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library unisim;
use unisim.vcomponents.all;

entity flash_ctl is
    port (
        clk          : in  std_logic;
        rst          : in  std_logic;

        cs           : in  std_logic;                      -- 1 = flash selected
        nbytes_m1    : in  std_logic_vector(1 downto 0);   -- bytes per transfer - 1
        go           : in  std_logic;                      -- toggle to start
        tx           : in  std_logic_vector(31 downto 0);
        rx           : out std_logic_vector(31 downto 0);
        busy         : out std_logic;

        reboot       : in  std_logic;                      -- pulse
        reboot_addr  : in  std_logic_vector(23 downto 0);

        image_id     : out std_logic_vector(31 downto 0);

        temp_raw     : out std_logic_vector(15 downto 0);
        vccint_raw   : out std_logic_vector(15 downto 0);
        vccaux_raw   : out std_logic_vector(15 downto 0);

        flash_cs_n   : out std_logic;
        flash_mosi   : out std_logic;
        flash_miso   : in  std_logic;
        flash_wp_n   : out std_logic;
        flash_hold_n : out std_logic
    );
end entity flash_ctl;

architecture rtl of flash_ctl is

    signal go_q     : std_logic := '0';
    signal run      : std_logic := '0';
    signal div      : unsigned(2 downto 0) := (others => '0');
    signal bits     : unsigned(5 downto 0) := (others => '0');
    signal sck      : std_logic := '0';
    signal sh_out   : std_logic_vector(31 downto 0) := (others => '0');
    signal sh_in    : std_logic_vector(31 downto 0) := (others => '0');
    signal miso_s   : std_logic_vector(1 downto 0) := "11";
    attribute ASYNC_REG : string;
    attribute ASYNC_REG of miso_s : signal is "TRUE";

    -- ICAPE2 wants each byte bit-reversed (UG470, parallel bus bit order).
    function swap (w : std_logic_vector(31 downto 0)) return std_logic_vector is
        variable r : std_logic_vector(31 downto 0);
    begin
        for b in 0 to 3 loop
            for i in 0 to 7 loop
                r(8*b + i) := w(8*b + 7 - i);
            end loop;
        end loop;
        return r;
    end function;

    type words_t is array (0 to 7) of std_logic_vector(31 downto 0);
    signal icap_step : unsigned(3 downto 0) := (others => '0');   -- 0 idle, 1 RDWRB low, 2..9 words, 10 done
    signal icap_addr : std_logic_vector(23 downto 0) := (others => '0');
    signal icap_csib : std_logic := '1';
    signal icap_rdwrb : std_logic := '1';
    signal icap_i    : std_logic_vector(31 downto 0) := (others => '1');

    signal mon_tick  : unsigned(15 downto 0) := (others => '0');
    signal mon_ch    : unsigned(1 downto 0) := "00";
    signal mon_den   : std_logic := '0';
    signal mon_drdy  : std_logic;
    signal mon_do    : std_logic_vector(15 downto 0);
    signal mon_daddr : std_logic_vector(6 downto 0);

begin

    busy         <= run or (go xor go_q);
    rx           <= sh_in;
    flash_cs_n   <= not cs;
    flash_mosi   <= sh_out(31);
    flash_wp_n   <= '1';
    flash_hold_n <= '1';

    spi : process (clk) is
    begin
        if rising_edge(clk) then
            miso_s <= miso_s(0) & flash_miso;
            if rst = '1' then
                run  <= '0';
                sck  <= '0';
                go_q <= go;
            elsif run = '0' then
                sck <= '0';
                if go /= go_q then
                    go_q   <= go;
                    run    <= '1';
                    div    <= (others => '0');
                    bits   <= (resize(unsigned(nbytes_m1), 3) + 1) & "000";
                    sh_out <= tx;
                    sh_in  <= (others => '0');
                end if;
            else
                -- one SPI bit per 8 clocks: SCK rises at div = 3, falls at div = 7
                div <= div + 1;
                if div = 3 then
                    sck   <= '1';
                    sh_in <= sh_in(30 downto 0) & miso_s(1);   -- data the flash put out on the previous falling edge
                elsif div = 7 then
                    sck    <= '0';
                    sh_out <= sh_out(30 downto 0) & '0';
                    bits   <= bits - 1;
                    if bits = 1 then
                        run <= '0';
                    end if;
                end if;
            end if;
        end if;
    end process;

    startup : STARTUPE2
        generic map (PROG_USR => "FALSE", SIM_CCLK_FREQ => 0.0)
        port map (
            CFGCLK => open, CFGMCLK => open, EOS => open, PREQ => open,
            CLK => '0', GSR => '0', GTS => '0', KEYCLEARB => '1', PACK => '0',
            USRCCLKO => sck, USRCCLKTS => '0',
            USRDONEO => '1', USRDONETS => '1');

    access_reg : USR_ACCESSE2
        port map (CFGCLK => open, DATA => image_id, DATAVALID => open);

    icap_fsm : process (clk) is
        variable w : words_t;
    begin
        if rising_edge(clk) then
            w := (x"FFFFFFFF", x"AA995566", x"20000000", x"30020001",
                  x"00000000", x"30008001", x"0000000F", x"20000000");
            w(4)(23 downto 0) := icap_addr;
            if rst = '1' then
                icap_step <= (others => '0');
                icap_csib <= '1';
                icap_rdwrb <= '1';
            elsif icap_step = 0 then
                icap_csib <= '1';
                icap_rdwrb <= '1';
                if reboot = '1' then
                    icap_addr <= reboot_addr;
                    icap_step <= to_unsigned(1, 4);
                end if;
            elsif icap_step = 1 then
                icap_rdwrb <= '0';
                icap_step <= icap_step + 1;
            elsif icap_step <= 9 then
                icap_csib <= '0';
                icap_i    <= swap(w(to_integer(icap_step) - 2));
                icap_step <= icap_step + 1;
            else
                icap_csib <= '1';                           -- the FPGA is reconfiguring by now
            end if;
        end if;
    end process;

    -- One DRP read every 2^16 clocks, round the three status registers.
    mon_daddr <= "00000" & std_logic_vector(mon_ch);
    monitor : process (clk) is
    begin
        if rising_edge(clk) then
            mon_tick <= mon_tick + 1;
            mon_den  <= '0';
            if mon_tick = 0 then
                mon_den <= '1';
            end if;
            if mon_drdy = '1' then
                case mon_ch is
                    when "00"   => temp_raw   <= mon_do;
                    when "01"   => vccint_raw <= mon_do;
                    when others => vccaux_raw <= mon_do;
                end case;
                if mon_ch = "10" then
                    mon_ch <= "00";
                else
                    mon_ch <= mon_ch + 1;
                end if;
            end if;
        end if;
    end process;

    -- Default mode (INIT_41 = 0): internal sensors with calibration, no
    -- external inputs. INIT_42: ADC clock = clk / 4 = 20 MHz (1 to 26 MHz).
    xadc_i : XADC
        generic map (INIT_40 => x"0000", INIT_41 => x"0000", INIT_42 => x"0400")
        port map (
            DCLK => clk, DEN => mon_den, DWE => '0', DADDR => mon_daddr,
            DI => x"0000", DO => mon_do, DRDY => mon_drdy,
            RESET => '0', CONVST => '0', CONVSTCLK => '0',
            VP => '0', VN => '0', VAUXP => x"0000", VAUXN => x"0000",
            ALM => open, BUSY => open, CHANNEL => open, EOC => open, EOS => open,
            JTAGBUSY => open, JTAGLOCKED => open, JTAGMODIFIED => open,
            MUXADDR => open, OT => open);

    icap : ICAPE2
        generic map (ICAP_WIDTH => "X32")
        port map (CLK => clk, CSIB => icap_csib, RDWRB => icap_rdwrb, I => icap_i, O => open);

end architecture rtl;
