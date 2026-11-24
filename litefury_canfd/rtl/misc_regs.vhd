-- BAR0 "board" registers for the LiteFury CAN FD card, laid out the way the
-- mainline Linux ctucanfd_pci driver expects (it was written for CTU's own
-- PCIe card, whose BAR0 holds an ID word and an Avalon-to-PCIe bridge's
-- interrupt enable register):
--
--   0x0000  ID            read-only, bits 3:0 = number of CAN cores (generic NUM_CORES)
--   0x4050  A2P_IE        read/write, bit 0 enables the interrupt to the host
--   0x4054  LEDS          read/write, bits 3:0 drive the user LEDs directly
--                         when bit 31 is set (otherwise status is shown, or
--                         a running light in the bootloader image)
--   0x4058  TIMESTAMP_LO  read-only, free-running counter (CAN clock)
--   0x405C  TIMESTAMP_HI  read-only
--
-- With HAS_FLASH (the artix_m2 card) it also gives the host the configuration
-- flash, for firmware updates over PCIe (sw/flash.py, see rtl/flash_ctl.vhd):
--
--   0x4060  FLASH_ID      read-only, 0x464C5348 "FLSH" if these registers exist, else 0
--   0x4064  FLASH_CTRL    bit 0: select the flash (CS low); bits 2:1: bytes per
--                         transfer - 1; bit 4: GO, a transfer starts when this
--                         bit changes; bit 5: AUTO_RX, every read of FLASH_RX
--                         also starts the next transfer; bit 6: AUTO_TX, every
--                         write of FLASH_TX starts a transfer; bit 31: busy
--   0x4068  FLASH_TX      bytes to send, first byte in bits 31:24
--   0x406C  FLASH_RX      bytes received, last byte in bits 7:0
--   0x4070  IMAGE_ID      read-only, the running bitstream's USR_ACCESS word:
--                         0x474F4C44 "GOLD" for the bootloader image, else a build time
--   0x4074  REBOOT        write 0xB7aaaaaa: reconfigure the FPGA from flash
--                         address aaaaaa (0 = as at power-up)
--
-- Bus accesses wait while a flash transfer is running (at most 3.2 us), so the
-- host needs no busy polling, and the AUTO bits make a bulk read one bus read
-- and a bulk write one bus write per four bytes. AXI does not order reads
-- against writes, so after writing FLASH_CTRL the host reads it back before it
-- relies on the new value (see sw/flash.py).
--
-- Also provides the 64-bit timestamp input of the CAN core and the LED
-- outputs. AXI4-Lite slave, single outstanding transaction.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity misc_regs is
    generic (
        NUM_CORES : natural range 1 to 15 := 1;
        HAS_FLASH : boolean := false
    );
    port (
        s_axi_aclk    : in  std_logic;
        s_axi_aresetn : in  std_logic;

        s_axi_awaddr  : in  std_logic_vector(15 downto 0);
        s_axi_awvalid : in  std_logic;
        s_axi_awready : out std_logic;
        s_axi_wdata   : in  std_logic_vector(31 downto 0);
        s_axi_wstrb   : in  std_logic_vector(3 downto 0);
        s_axi_wvalid  : in  std_logic;
        s_axi_wready  : out std_logic;
        s_axi_bresp   : out std_logic_vector(1 downto 0);
        s_axi_bvalid  : out std_logic;
        s_axi_bready  : in  std_logic;
        s_axi_araddr  : in  std_logic_vector(15 downto 0);
        s_axi_arvalid : in  std_logic;
        s_axi_arready : out std_logic;
        s_axi_rdata   : out std_logic_vector(31 downto 0);
        s_axi_rresp   : out std_logic_vector(1 downto 0);
        s_axi_rvalid  : out std_logic;
        s_axi_rready  : in  std_logic;

        irq_enable    : out std_logic;
        timestamp     : out std_logic_vector(63 downto 0);
        link_up       : in  std_logic;
        can_irq       : in  std_logic_vector(NUM_CORES - 1 downto 0);
        leds          : out std_logic_vector(3 downto 0);

        -- configuration flash (HAS_FLASH); the clock goes out through STARTUPE2
        flash_cs_n    : out std_logic;
        flash_mosi    : out std_logic;
        flash_miso    : in  std_logic := '1';
        flash_wp_n    : out std_logic;
        flash_hold_n  : out std_logic
    );

    -- Interface hints for the Vivado block design (module reference).
    attribute X_INTERFACE_INFO      : string;
    attribute X_INTERFACE_PARAMETER : string;
    attribute X_INTERFACE_INFO of s_axi_aclk : signal is
        "xilinx.com:signal:clock:1.0 s_axi_aclk CLK";
    attribute X_INTERFACE_PARAMETER of s_axi_aclk : signal is
        "ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET s_axi_aresetn";
    attribute X_INTERFACE_INFO of s_axi_aresetn : signal is
        "xilinx.com:signal:reset:1.0 s_axi_aresetn RST";
    attribute X_INTERFACE_PARAMETER of s_axi_aresetn : signal is
        "POLARITY ACTIVE_LOW";
end entity misc_regs;

architecture rtl of misc_regs is

    constant ADDR_ID     : unsigned(15 downto 0) := x"0000";
    constant ADDR_A2P_IE : unsigned(15 downto 0) := x"4050";
    constant ADDR_LEDS   : unsigned(15 downto 0) := x"4054";
    constant ADDR_TS_LO  : unsigned(15 downto 0) := x"4058";
    constant ADDR_TS_HI  : unsigned(15 downto 0) := x"405C";
    constant ADDR_FL_ID  : unsigned(15 downto 0) := x"4060";
    constant ADDR_FL_CTL : unsigned(15 downto 0) := x"4064";
    constant ADDR_FL_TX  : unsigned(15 downto 0) := x"4068";
    constant ADDR_FL_RX  : unsigned(15 downto 0) := x"406C";
    constant ADDR_IMAGE  : unsigned(15 downto 0) := x"4070";
    constant ADDR_REBOOT : unsigned(15 downto 0) := x"4074";

    signal fl_ctl    : std_logic_vector(7 downto 0) := (others => '0');
    signal fl_tx     : std_logic_vector(31 downto 0) := (others => '0');
    signal fl_rx     : std_logic_vector(31 downto 0) := (others => '0');
    signal fl_busy   : std_logic := '0';
    signal fl_kick   : std_logic := '0';
    signal fl_go     : std_logic;
    signal fl_id     : std_logic_vector(31 downto 0) := (others => '0');
    signal image_id  : std_logic_vector(31 downto 0) := (others => '0');
    signal reboot    : std_logic := '0';
    signal reboot_addr : std_logic_vector(23 downto 0) := (others => '0');
    signal rst       : std_logic;
    signal is_gold   : std_logic;
    signal chase     : std_logic_vector(3 downto 0);

    signal a2p_ie   : std_logic_vector(31 downto 0) := (others => '0');
    signal led_reg  : std_logic_vector(31 downto 0) := (others => '0');
    signal ts       : unsigned(63 downto 0) := (others => '0');

    signal awready, wready, bvalid, arready, rvalid : std_logic := '0';
    signal rdata    : std_logic_vector(31 downto 0) := (others => '0');
    signal waddr    : unsigned(15 downto 0) := (others => '0');
    signal aw_got, w_got : std_logic := '0';
    signal wdata_l  : std_logic_vector(31 downto 0) := (others => '0');
    signal wstrb_l  : std_logic_vector(3 downto 0) := (others => '0');

    -- irq LED stretched so short interrupts are visible
    signal irq_stretch : unsigned(21 downto 0) := (others => '0');

    -- link_up comes from the PCIe clock domain
    signal link_up_s : std_logic_vector(1 downto 0) := "00";
    attribute ASYNC_REG : string;
    attribute ASYNC_REG of link_up_s : signal is "TRUE";

begin

    s_axi_awready <= awready;
    s_axi_wready  <= wready;
    s_axi_bvalid  <= bvalid;
    s_axi_bresp   <= "00";
    s_axi_arready <= arready;
    s_axi_rvalid  <= rvalid;
    s_axi_rdata   <= rdata;
    s_axi_rresp   <= "00";

    irq_enable <= a2p_ie(0);
    rst        <= not s_axi_aresetn;
    fl_go      <= fl_ctl(4) xor fl_kick;

    gen_flash : if HAS_FLASH generate
        fl_id <= x"464C5348";
        flash : entity work.flash_ctl
            port map (
                clk => s_axi_aclk, rst => rst,
                cs => fl_ctl(0), nbytes_m1 => fl_ctl(2 downto 1), go => fl_go,
                tx => fl_tx, rx => fl_rx, busy => fl_busy,
                reboot => reboot, reboot_addr => reboot_addr,
                image_id => image_id,
                flash_cs_n => flash_cs_n, flash_mosi => flash_mosi, flash_miso => flash_miso,
                flash_wp_n => flash_wp_n, flash_hold_n => flash_hold_n);
    end generate;
    gen_no_flash : if not HAS_FLASH generate
        flash_cs_n   <= '1';
        flash_mosi   <= '1';
        flash_wp_n   <= '1';
        flash_hold_n <= '1';
    end generate;
    timestamp  <= std_logic_vector(ts);

    -- LEDs on the LiteFury are wired to 3.3 V through a resistor: drive low
    -- to light. Default view: link up, CAN irq activity, heartbeat, irq enabled.
    -- The bootloader image (IMAGE_ID "GOLD") instead runs one light along
    -- LED 1, 2, 3, 4, about 0.2 s each, so a card that fell back to it shows.
    leds <= not led_reg(3 downto 0) when led_reg(31) = '1' else
            not chase when is_gold = '1' else
            not (a2p_ie(0) & ts(25) & irq_stretch(21) & link_up_s(1));
    is_gold <= '1' when HAS_FLASH and image_id = x"474F4C44" else '0';
    with ts(25 downto 24) select chase <=
        "0001" when "00", "0010" when "01", "0100" when "10", "1000" when others;

    process (s_axi_aclk) is
    begin
        if rising_edge(s_axi_aclk) then
            link_up_s <= link_up_s(0) & link_up;
            ts <= ts + 1;
            if unsigned(can_irq) /= 0 then
                irq_stretch <= (others => '1');
            elsif irq_stretch /= 0 then
                irq_stretch <= irq_stretch - 1;
            end if;

            reboot <= '0';
            if s_axi_aresetn = '0' then
                awready <= '0'; wready <= '0'; bvalid <= '0';
                arready <= '0'; rvalid <= '0';
                aw_got <= '0'; w_got <= '0';
                a2p_ie <= (others => '0');
                led_reg <= (others => '0');
                fl_ctl <= (others => '0');
            else
                -- Write: accept address and data (in any order), then respond.
                awready <= '0';
                wready  <= '0';
                if s_axi_awvalid = '1' and aw_got = '0' and bvalid = '0' then
                    waddr   <= unsigned(s_axi_awaddr);
                    aw_got  <= '1';
                    awready <= '1';
                end if;
                if s_axi_wvalid = '1' and w_got = '0' and bvalid = '0' then
                    wdata_l <= s_axi_wdata;
                    wstrb_l <= s_axi_wstrb;
                    w_got   <= '1';
                    wready  <= '1';
                end if;
                if aw_got = '1' and w_got = '1' and bvalid = '0' and fl_busy = '0' then
                    if waddr = ADDR_FL_CTL and wstrb_l(0) = '1' then
                        fl_ctl <= wdata_l(7 downto 0);
                    end if;
                    if waddr = ADDR_FL_TX and wstrb_l = "1111" and fl_ctl(6) = '1' then
                        fl_kick <= not fl_kick;
                    end if;
                    if waddr = ADDR_REBOOT and wstrb_l = "1111" and wdata_l(31 downto 24) = x"B7" then
                        reboot      <= '1';
                        reboot_addr <= wdata_l(23 downto 0);
                    end if;
                    for b in 0 to 3 loop
                        if wstrb_l(b) = '1' then
                            case waddr is
                                when ADDR_A2P_IE => a2p_ie(8*b+7 downto 8*b)  <= wdata_l(8*b+7 downto 8*b);
                                when ADDR_LEDS   => led_reg(8*b+7 downto 8*b) <= wdata_l(8*b+7 downto 8*b);
                                when ADDR_FL_TX  => fl_tx(8*b+7 downto 8*b)   <= wdata_l(8*b+7 downto 8*b);
                                when others      => null;
                            end case;
                        end if;
                    end loop;
                    bvalid <= '1';
                    aw_got <= '0';
                    w_got  <= '0';
                end if;
                if bvalid = '1' and s_axi_bready = '1' then
                    bvalid <= '0';
                end if;

                -- Read
                arready <= '0';
                if s_axi_arvalid = '1' and rvalid = '0' and arready = '0' and fl_busy = '0' then
                    arready <= '1';
                    rvalid  <= '1';
                    if unsigned(s_axi_araddr) = ADDR_FL_RX and fl_ctl(5) = '1' then
                        fl_kick <= not fl_kick;
                    end if;
                    case unsigned(s_axi_araddr) is
                        when ADDR_ID     => rdata <= std_logic_vector(to_unsigned(NUM_CORES, 32));
                        when ADDR_A2P_IE => rdata <= a2p_ie;
                        when ADDR_LEDS   => rdata <= led_reg;
                        when ADDR_TS_LO  => rdata <= std_logic_vector(ts(31 downto 0));
                        when ADDR_TS_HI  => rdata <= std_logic_vector(ts(63 downto 32));
                        when ADDR_FL_ID  => rdata <= fl_id;
                        when ADDR_FL_CTL => rdata <= fl_busy & x"000000" & fl_ctl(6 downto 0);
                        when ADDR_FL_TX  => rdata <= fl_tx;
                        when ADDR_FL_RX  => rdata <= fl_rx;
                        when ADDR_IMAGE  => rdata <= image_id;
                        when others      => rdata <= (others => '0');
                    end case;
                end if;
                if rvalid = '1' and s_axi_rready = '1' then
                    rvalid <= '0';
                end if;
            end if;
        end if;
    end process;

end architecture rtl;
