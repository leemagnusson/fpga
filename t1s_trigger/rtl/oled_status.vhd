-- Status display subsystem: per-event rate counters, the text screen and the
-- Pmod OLEDrgb driver. Pulled out of top so the simulation can feed it
-- synthetic events.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.trig_screen_pkg.all;

entity oled_status is
    generic (
        CLKS_PER_MS : positive := 100_000;
        SPI_DIV     : positive := 16
    );
    port (
        clk         : in  std_logic;
        sec_tick    : in  std_logic;                              -- once per second
        sw          : in  std_logic_vector(15 downto 0);
        plca_synced : in  std_logic;
        events      : in  std_logic_vector(N_RATES - 1 downto 0);  -- one-clock pulses, see trig_screen
        sqi_last    : in  unsigned(4 downto 0) := (others => '0');
        sqi_min     : in  unsigned(4 downto 0) := (others => '0');
        frame       : out std_logic;
        -- Pmod OLEDrgb
        cs_n, mosi, sck, dc, res_n, vccen, pmoden : out std_logic
    );
end entity oled_status;

architecture rtl of oled_status is
    signal rates  : t_rates(0 to N_RATES - 1);
    signal px_x   : unsigned(6 downto 0);
    signal px_y   : unsigned(5 downto 0);
    signal px_rgb : std_logic_vector(15 downto 0);
begin
    g_rate : for i in 0 to N_RATES - 1 generate
        u_r : entity work.bcd_rate generic map (DIGITS => 5)
            port map (clk => clk, pulse => events(i), tick => sec_tick, bcd => rates(i));
    end generate;

    u_screen : entity work.trig_screen
        port map (clk => clk, sw => sw, plca_synced => plca_synced, rates => rates,
                  sqi_last => sqi_last, sqi_min => sqi_min,
                  px_x => px_x, px_y => px_y, px_rgb => px_rgb);

    u_oled : entity work.oled_ssd1331
        generic map (CLKS_PER_MS => CLKS_PER_MS, SPI_DIV => SPI_DIV)
        port map (clk => clk, px_x => px_x, px_y => px_y, px_rgb => px_rgb, frame => frame,
                  cs_n => cs_n, mosi => mosi, sck => sck, dc => dc,
                  res_n => res_n, vccen => vccen, pmoden => pmoden);
end architecture rtl;
