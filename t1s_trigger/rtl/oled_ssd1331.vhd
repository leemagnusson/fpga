-- Driver for the Digilent Pmod OLEDrgb (SSD1331, 96x64, 16-bit colour).
--
-- Runs the power-up sequence from Digilent's PmodOLEDrgb driver (unlock,
-- Univision init table, clear, VCCEN, display on, with their delays), then
-- streams the whole frame over SPI for ever: each frame re-sends the column
-- and row window and then 96*64 pixels, RGB565, high byte first. The picture
-- comes from a client: the driver presents the coordinates of the pixel it
-- will send next (px_x, px_y) and samples px_rgb when it starts that pixel,
-- i.e. the client has one pixel time (32 SPI bits) to answer.
--
-- SPI mode 0, MSB first, SCK = clk / SPI_DIV (SSD1331 minimum cycle 150 ns,
-- so SPI_DIV >= 16 at 100 MHz). CS is held low while a command list or a
-- frame is being sent. Pmod OLEDrgb pins: 1 CS, 2 MOSI, 4 SCK, 7 D/C,
-- 8 RES, 9 VCCEN, 10 PMODEN.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity oled_ssd1331 is
    generic (
        CLKS_PER_MS : positive := 100_000;   -- clk cycles in a millisecond (shrink in simulation)
        SPI_DIV     : positive := 16         -- clk cycles per SPI bit, even, >= 2
    );
    port (
        clk     : in  std_logic;
        -- picture source
        px_x    : out unsigned(6 downto 0);  -- 0..95
        px_y    : out unsigned(5 downto 0);  -- 0..63
        px_rgb  : in  std_logic_vector(15 downto 0);
        frame   : out std_logic := '0';      -- pulse at the start of each frame
        -- Pmod
        cs_n    : out std_logic := '1';
        mosi    : out std_logic := '0';
        sck     : out std_logic := '0';
        dc      : out std_logic := '0';      -- 0 command, 1 data
        res_n   : out std_logic := '1';
        vccen   : out std_logic := '0';
        pmoden  : out std_logic := '0'
    );
end entity oled_ssd1331;

architecture rtl of oled_ssd1331 is
    type t_bytes is array (natural range <>) of std_logic_vector(7 downto 0);

    -- Digilent OLEDrgb_DevInit command list (after the unlock) ...
    constant INIT : t_bytes := (
        x"FD", x"12",          -- unlock
        x"AE",                 -- display off
        x"A0", x"72",          -- remap: RGB, 65k colour format 1, (0,0) top left
        x"A1", x"00",          -- start line
        x"A2", x"00",          -- display offset
        x"A4",                 -- normal display
        x"A8", x"3F",          -- multiplex 64
        x"AD", x"8E",          -- master configuration
        x"B0", x"0B",          -- power save
        x"B1", x"31",          -- phase 1/2 periods
        x"B3", x"F0",          -- clock divide / oscillator
        x"8A", x"64", x"8B", x"78", x"8C", x"64",   -- second precharge A, B, C
        x"BB", x"3A",          -- precharge level
        x"BE", x"3E",          -- VCOMH
        x"87", x"06",          -- master current
        x"81", x"91", x"82", x"50", x"83", x"7D",   -- contrast A, B, C
        x"2E",                 -- scrolling off
        x"25", x"00", x"00", x"5F", x"3F"           -- clear window 0,0 - 95,63
    );
    -- ... and the window set before every frame
    constant WINDOW : t_bytes := (x"15", x"00", x"5F", x"75", x"00", x"3F");

    type t_state is (S_POWER, S_RESET_LO, S_RESET_HI, S_INIT, S_VCC, S_ON, S_ON_WAIT,
                     S_WINDOW, S_PIXELS);
    signal state   : t_state := S_POWER;
    signal ms_cnt  : natural range 0 to CLKS_PER_MS - 1 := 0;
    signal ms_left : natural range 0 to 127 := 20;
    signal idx     : natural range 0 to INIT'length := 0;

    -- byte shifter
    signal busy    : std_logic := '0';
    signal sreg    : std_logic_vector(7 downto 0) := (others => '0');
    signal bit_cnt : natural range 0 to 7 := 0;
    signal div_cnt : natural range 0 to SPI_DIV - 1 := 0;
    signal load    : std_logic := '0';
    signal load_byte : std_logic_vector(7 downto 0) := (others => '0');
    signal done    : std_logic := '0';          -- one clock when a byte finishes

    signal x       : unsigned(6 downto 0) := (others => '0');
    signal y       : unsigned(5 downto 0) := (others => '0');
    signal pix     : std_logic_vector(15 downto 0) := (others => '0');
    signal hi_byte : std_logic := '1';
begin
    px_x <= x;
    px_y <= y;

    -- SPI byte shifter, mode 0: data changes on the falling edge, is sampled
    -- on the rising edge. sck stays low between bytes, CS is managed by the
    -- sequencer.
    process (clk)
    begin
        if rising_edge(clk) then
            done <= '0';
            if load = '1' then
                sreg    <= load_byte;
                busy    <= '1';
                bit_cnt <= 7;
                div_cnt <= 0;
                sck     <= '0';
                mosi    <= load_byte(7);
            elsif busy = '1' then
                if div_cnt = SPI_DIV - 1 then
                    div_cnt <= 0;
                else
                    div_cnt <= div_cnt + 1;
                end if;
                if div_cnt = SPI_DIV / 2 - 1 then
                    sck <= '1';                                 -- rising edge: slave samples
                elsif div_cnt = SPI_DIV - 1 then
                    sck <= '0';                                 -- falling edge: next bit
                    if bit_cnt = 0 then
                        busy <= '0';
                        done <= '1';
                    else
                        bit_cnt <= bit_cnt - 1;
                        mosi    <= sreg(bit_cnt - 1);
                    end if;
                end if;
            end if;
        end if;
    end process;

    -- sequencer
    process (clk)
        procedure wait_ms(n : natural) is
        begin
            ms_left <= n;
            ms_cnt  <= 0;
        end procedure;
        variable ms_done : boolean;
    begin
        if rising_edge(clk) then
            load  <= '0';
            frame <= '0';

            -- millisecond timer, counts ms_left down to 0
            ms_done := false;
            if ms_left /= 0 then
                if ms_cnt = CLKS_PER_MS - 1 then
                    ms_cnt  <= 0;
                    ms_left <= ms_left - 1;
                    ms_done := ms_left = 1;
                else
                    ms_cnt <= ms_cnt + 1;
                end if;
            end if;

            case state is
                when S_POWER =>                 -- PMODEN high, RES high, 20 ms for VDD
                    pmoden <= '1';
                    res_n  <= '1';
                    dc     <= '0';
                    cs_n   <= '1';
                    if ms_left = 0 and ms_cnt = 0 then
                        wait_ms(20);
                    elsif ms_done then
                        res_n <= '0';
                        wait_ms(1);
                        state <= S_RESET_LO;
                    end if;

                when S_RESET_LO =>
                    if ms_done then
                        res_n <= '1';
                        wait_ms(2);
                        state <= S_RESET_HI;
                    end if;

                when S_RESET_HI =>
                    if ms_done then
                        idx   <= 0;
                        cs_n  <= '0';
                        state <= S_INIT;
                    end if;

                when S_INIT =>                  -- send the command list
                    if busy = '0' and load = '0' then
                        if idx = INIT'length then
                            cs_n  <= '1';
                            vccen <= '1';       -- panel supply on, 25 ms to settle
                            wait_ms(25);
                            state <= S_VCC;
                        else
                            load      <= '1';
                            load_byte <= INIT(idx);
                            idx       <= idx + 1;
                        end if;
                    end if;

                when S_VCC =>
                    if ms_done then
                        cs_n      <= '0';
                        load      <= '1';
                        load_byte <= x"AF";     -- display on
                        state     <= S_ON;
                    end if;

                when S_ON =>
                    if done = '1' then
                        cs_n <= '1';
                        wait_ms(100);
                        state <= S_ON_WAIT;
                    end if;

                when S_ON_WAIT =>
                    if ms_done then
                        idx   <= 0;
                        cs_n  <= '0';
                        state <= S_WINDOW;
                    end if;

                when S_WINDOW =>                -- column 0..95, row 0..63, then pixels
                    -- dc changes together with the load of the first byte it applies
                    -- to, i.e. before that byte's first clock edge
                    if busy = '0' and load = '0' then
                        if idx = WINDOW'length then
                            dc      <= '1';
                            x       <= (others => '0');
                            y       <= (others => '0');
                            pix     <= px_rgb;  -- pixel (0,0), coordinates were 0,0 already
                            hi_byte <= '1';
                            frame   <= '1';
                            state   <= S_PIXELS;
                        else
                            dc        <= '0';
                            load      <= '1';
                            load_byte <= WINDOW(idx);
                            idx       <= idx + 1;
                        end if;
                    end if;

                when S_PIXELS =>
                    if busy = '0' and load = '0' then
                        load <= '1';
                        if hi_byte = '1' then
                            load_byte <= pix(15 downto 8);
                            hi_byte   <= '0';
                            -- advance the request so the client has a byte time to answer
                            if x = 95 then
                                x <= (others => '0');
                                if y = 63 then
                                    y <= (others => '0');
                                else
                                    y <= y + 1;
                                end if;
                            else
                                x <= x + 1;
                            end if;
                        else
                            load_byte <= pix(7 downto 0);
                            hi_byte   <= '1';
                            pix       <= px_rgb;    -- colour of the pixel requested above
                            if x = 0 and y = 0 then
                                -- the frame wrapped: next pixel is (0,0); re-send the window
                                -- so the GDDRAM pointer can never drift
                                idx   <= 0;
                                state <= S_WINDOW;
                            end if;
                        end if;
                    end if;
            end case;
        end if;
    end process;
end architecture rtl;
