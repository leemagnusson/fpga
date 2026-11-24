-- Testbench for the flash access in misc_regs / flash_ctl (GHDL, run by
-- ci/check.sh with the unisim stubs from ci/unisim_stub.vhd): single and
-- AUTO transfers against a simple SPI slave with worst-case clock-to-output
-- delays, and the IPROG sequence sent to ICAPE2 by the reboot register.
--
--   ghdl -a --std=08 --work=unisim ci/unisim_stub.vhd
--   ghdl -a --std=08 -P. litefury_canfd/rtl/flash_ctl.vhd litefury_canfd/rtl/misc_regs.vhd litefury_canfd/sim/flash_tb.vhd
--   ghdl --elab-run --std=08 -P. flash_tb --assert-level=error

library ieee; use ieee.std_logic_1164.all; use ieee.numeric_std.all;
library unisim; use unisim.sim_probe.all;
entity flash_tb is end entity;
architecture sim of flash_tb is
    signal clk : std_logic := '0'; signal rstn : std_logic := '0';
    signal awaddr, araddr : std_logic_vector(15 downto 0) := (others => '0');
    signal awvalid, awready, wvalid, wready, bvalid, bready, arvalid, arready, rvalid, rready : std_logic := '0';
    signal wdata, rdata : std_logic_vector(31 downto 0) := (others => '0');
    signal wstrb : std_logic_vector(3 downto 0) := "1111";
    signal cs_n, mosi, miso, wp_n, hold_n : std_logic;
    signal leds : std_logic_vector(3 downto 0);
    signal done : boolean := false;
    type bytes_t is array (0 to 63) of std_logic_vector(7 downto 0);
    signal mosi_log : bytes_t := (others => x"00");
    signal mosi_n : natural := 0;
    signal icap_log : bytes_t := (others => x"00");
    signal nclk : natural := 0;        -- SPI clocks seen at the pin
begin
    clk <= not clk after 6.25 ns when not done;
    dut : entity work.misc_regs generic map (NUM_CORES => 4, HAS_FLASH => true)
        port map (s_axi_aclk => clk, s_axi_aresetn => rstn,
            s_axi_awaddr => awaddr, s_axi_awvalid => awvalid, s_axi_awready => awready,
            s_axi_wdata => wdata, s_axi_wstrb => wstrb, s_axi_wvalid => wvalid, s_axi_wready => wready,
            s_axi_bresp => open, s_axi_bvalid => bvalid, s_axi_bready => bready,
            s_axi_araddr => araddr, s_axi_arvalid => arvalid, s_axi_arready => arready,
            s_axi_rdata => rdata, s_axi_rresp => open, s_axi_rvalid => rvalid, s_axi_rready => rready,
            irq_enable => open, timestamp => open, link_up => '1', can_irq => "0000", leds => leds,
            flash_cs_n => cs_n, flash_mosi => mosi, flash_miso => miso, flash_wp_n => wp_n, flash_hold_n => hold_n);

    -- SPI slave: logs MOSI bytes, answers 0x80, 0x81, ... from the first byte after CS falls
    slave : process
        variable sh : std_logic_vector(7 downto 0); variable n : natural; variable k : natural; variable outb : std_logic_vector(7 downto 0);
    begin
        miso <= 'Z';
        wait until falling_edge(cs_n);
        n := 0; k := 0; outb := x"80"; miso <= outb(7);
        loop
            wait until rising_edge(cclk) or rising_edge(cs_n);
            exit when cs_n = '1';
            sh := sh(6 downto 0) & mosi; n := n + 1; nclk <= nclk + 1;
            if n = 8 then mosi_log(mosi_n) <= sh; mosi_n <= mosi_n + 1; n := 0; end if;
            wait until falling_edge(cclk) or rising_edge(cs_n);
            exit when cs_n = '1';
            if n = 0 then k := k + 1; outb := std_logic_vector(to_unsigned(128 + k, 8)); else outb := outb(6 downto 0) & '0'; end if;
            miso <= transport outb(7) after 8 ns;      -- flash clock-to-output
        end loop;
    end process;

    icapmon : process (clk)
        variable n : natural := 0;
    begin
        if rising_edge(clk) and icap_strobe = '1' then
            for b in 0 to 3 loop
                for i in 0 to 7 loop icap_log(n*4 + (3-b))(i) <= icap_word(8*b + 7 - i); end loop;
            end loop;
            n := n + 1;
        end if;
    end process;

    stim : process
        procedure wr (a : std_logic_vector(15 downto 0); d : std_logic_vector(31 downto 0)) is
        begin
            awaddr <= a; wdata <= d; awvalid <= '1'; wvalid <= '1'; bready <= '1';
            loop wait until rising_edge(clk); if awready = '1' then awvalid <= '0'; end if; if wready = '1' then wvalid <= '0'; end if; exit when bvalid = '1'; end loop;
            awvalid <= '0'; wvalid <= '0'; wait until rising_edge(clk); bready <= '0';
        end procedure;
        procedure rd (a : std_logic_vector(15 downto 0); d : out std_logic_vector(31 downto 0)) is
        begin
            araddr <= a; arvalid <= '1'; rready <= '1';
            loop wait until rising_edge(clk); if arready = '1' then arvalid <= '0'; end if; exit when rvalid = '1'; end loop;
            d := rdata; arvalid <= '0'; wait until rising_edge(clk); rready <= '0';
        end procedure;
        variable v : std_logic_vector(31 downto 0);
        procedure chk (what : string; got, exp : std_logic_vector(31 downto 0)) is
        begin
            assert got = exp report what & ": got " & to_hstring(got) & " expected " & to_hstring(exp) severity error;
            if got = exp then report what & " ok " & to_hstring(got) severity note; end if;
        end procedure;
    begin
        wait for 100 ns; rstn <= '1'; wait for 100 ns;
        rd(x"4060", v); chk("FLASH_ID", v, x"464C5348");
        rd(x"4070", v); chk("IMAGE_ID", v, x"474F4C44");
        rd(x"0000", v); chk("ID", v, x"00000004");
        -- bootloader image (the stub's USR_ACCESS is "GOLD"): running light, first LED at the start; host override wins
        chk("LEDs bootloader", x"0000000" & leds, x"0000000E");
        wr(x"4054", x"80000005"); wait until rising_edge(clk);
        chk("LEDs host", x"0000000" & leds, x"0000000A");
        wr(x"4054", x"00000000");
        -- 1-byte transfer with CS: JEDEC-style
        wr(x"4068", x"9F000000"); wr(x"4064", x"00000011");            -- cs, n=1, go=1
        rd(x"4064", v); chk("CTRL after go", v, x"00000011");
        rd(x"406C", v); chk("RX 1 byte", v, x"00000080");
        -- 4-byte transfer, CS still low
        wr(x"4068", x"11223344"); wr(x"4064", x"00000007");            -- cs, n=4, go=0 (toggle)
        rd(x"406C", v); chk("RX 4 bytes", v, x"81828384");
        -- 3-byte transfer
        wr(x"4068", x"AABBCCDD"); wr(x"4064", x"00000015");            -- cs, n=3, go=1
        rd(x"406C", v); chk("RX 3 bytes", v, x"00858687");
        -- AUTO_RX, n=4: each RX read returns the last transfer and starts the next
        wr(x"4068", x"00000000"); wr(x"4064", x"00000037");            -- cs, n=4, go=1 (unchanged), auto_rx
        rd(x"4064", v); chk("CTRL auto_rx", v, x"00000037");
        rd(x"406C", v); chk("auto RX read 0 (stale)", v, x"00858687");
        rd(x"406C", v); chk("auto RX read 1", v, x"88898A8B");
        rd(x"406C", v); chk("auto RX read 2", v, x"8C8D8E8F");
        wr(x"4064", x"00000017");                                       -- auto off (go unchanged), waits for the kicked transfer
        rd(x"406C", v); chk("RX after auto off", v, x"90919293");
        wr(x"4064", x"00000000");                                       -- CS high
        -- AUTO_TX, n=4
        wr(x"4064", x"00000047");                                       -- cs, n=4, auto_tx, go=0
        wr(x"4068", x"02001000"); wr(x"4068", x"DEADBEEF"); wr(x"4068", x"01020304");
        wr(x"4064", x"00000000");
        wait for 200 ns;
        assert mosi_n = 32 report "mosi byte count " & integer'image(mosi_n) severity error;
        chk("MOSI 0..3", mosi_log(0) & mosi_log(1) & mosi_log(2) & mosi_log(3), x"9F112233");
        chk("MOSI 4..7", mosi_log(4) & mosi_log(5) & mosi_log(6) & mosi_log(7), x"44AABBCC");
        chk("MOSI 20..23 (auto tx)", mosi_log(20) & mosi_log(21) & mosi_log(22) & mosi_log(23), x"02001000");
        chk("MOSI 24..27", mosi_log(24) & mosi_log(25) & mosi_log(26) & mosi_log(27), x"DEADBEEF");
        chk("MOSI 28..31", mosi_log(28) & mosi_log(29) & mosi_log(30) & mosi_log(31), x"01020304");
        -- reboot with a wrong key does nothing, with the key sends IPROG
        wr(x"4074", x"00400000"); wait for 300 ns;
        chk("ICAP untouched", icap_log(4) & icap_log(5) & icap_log(6) & icap_log(7), x"00000000");
        wr(x"4074", x"B7400000"); wait for 400 ns;
        chk("ICAP w0", icap_log(0) & icap_log(1) & icap_log(2) & icap_log(3), x"FFFFFFFF");
        chk("ICAP w1", icap_log(4) & icap_log(5) & icap_log(6) & icap_log(7), x"AA995566");
        chk("ICAP w2", icap_log(8) & icap_log(9) & icap_log(10) & icap_log(11), x"20000000");
        chk("ICAP w3", icap_log(12) & icap_log(13) & icap_log(14) & icap_log(15), x"30020001");
        chk("ICAP w4", icap_log(16) & icap_log(17) & icap_log(18) & icap_log(19), x"00400000");
        chk("ICAP w5", icap_log(20) & icap_log(21) & icap_log(22) & icap_log(23), x"30008001");
        chk("ICAP w6", icap_log(24) & icap_log(25) & icap_log(26) & icap_log(27), x"0000000F");
        chk("ICAP w7", icap_log(28) & icap_log(29) & icap_log(30) & icap_log(31), x"20000000");
        chk("ICAP nothing after", icap_log(32) & icap_log(33) & icap_log(34) & icap_log(35), x"00000000");
        report "DONE";
        done <= true; wait;
    end process;
end architecture;
