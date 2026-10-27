-- BAR0 "board" registers for the LiteFury CAN FD card, laid out the way the
-- mainline Linux ctucanfd_pci driver expects (it was written for CTU's own
-- PCIe card, whose BAR0 holds an ID word and an Avalon-to-PCIe bridge's
-- interrupt enable register):
--
--   0x0000  ID            read-only, bits 3:0 = number of CAN cores (1)
--   0x4050  A2P_IE        read/write, bit 0 enables the interrupt to the host
--   0x4054  LEDS          read/write, bits 3:0 drive the user LEDs directly
--                         when bit 31 is set (otherwise status is shown)
--   0x4058  TIMESTAMP_LO  read-only, free-running counter (CAN clock)
--   0x405C  TIMESTAMP_HI  read-only
--
-- Also provides the 64-bit timestamp input of the CAN core and the LED
-- outputs. AXI4-Lite slave, single outstanding transaction.

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity misc_regs is
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
        can_irq       : in  std_logic;
        leds          : out std_logic_vector(3 downto 0)
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
    timestamp  <= std_logic_vector(ts);

    -- LEDs on the LiteFury are wired to 3.3 V through a resistor: drive low
    -- to light. Default view: link up, CAN irq activity, heartbeat, irq enabled.
    leds <= not led_reg(3 downto 0) when led_reg(31) = '1' else
            not (a2p_ie(0) & ts(25) & irq_stretch(21) & link_up_s(1));

    process (s_axi_aclk) is
    begin
        if rising_edge(s_axi_aclk) then
            link_up_s <= link_up_s(0) & link_up;
            ts <= ts + 1;
            if can_irq = '1' then
                irq_stretch <= (others => '1');
            elsif irq_stretch /= 0 then
                irq_stretch <= irq_stretch - 1;
            end if;

            if s_axi_aresetn = '0' then
                awready <= '0'; wready <= '0'; bvalid <= '0';
                arready <= '0'; rvalid <= '0';
                aw_got <= '0'; w_got <= '0';
                a2p_ie <= (others => '0');
                led_reg <= (others => '0');
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
                if aw_got = '1' and w_got = '1' and bvalid = '0' then
                    for b in 0 to 3 loop
                        if wstrb_l(b) = '1' then
                            case waddr is
                                when ADDR_A2P_IE => a2p_ie(8*b+7 downto 8*b)  <= wdata_l(8*b+7 downto 8*b);
                                when ADDR_LEDS   => led_reg(8*b+7 downto 8*b) <= wdata_l(8*b+7 downto 8*b);
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
                if s_axi_arvalid = '1' and rvalid = '0' and arready = '0' then
                    arready <= '1';
                    rvalid  <= '1';
                    case unsigned(s_axi_araddr) is
                        when ADDR_ID     => rdata <= x"00000001";
                        when ADDR_A2P_IE => rdata <= a2p_ie;
                        when ADDR_LEDS   => rdata <= led_reg;
                        when ADDR_TS_LO  => rdata <= std_logic_vector(ts(31 downto 0));
                        when ADDR_TS_HI  => rdata <= std_logic_vector(ts(63 downto 32));
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
