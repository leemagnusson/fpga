create_clock -period 10.000 -name clk_100m -waveform {0.000 5.000} [get_ports clk]
set_input_jitter clk_100m 0.200

# The line input is asynchronous and goes through a synchroniser; switches
# and buttons are static or debounced; the outputs are pulses with no
# reference clock at the receiving instrument.
set_false_path -from [get_ports {ja1_rx ja10_rxn sw[*] btn*}]
set_false_path -to   [get_ports {led[*] seg[*] dp an[*] ja2_trig0 ja3_trig1 ja4_trig2 ja7_trig3 ja8_de ja9_txd}]
# OLED SPI runs at clk/16 with data and clock launched from the same register stage.
set_false_path -to   [get_ports {jb*}]

# 250 MHz oversampling clocks from the MMCM in clk_gen. Everything that crosses
# between them and the 100 MHz clock goes through the toggle/holding-register
# handshake in sqi_calc, so the domains are declared asynchronous.
set_clock_groups -asynchronous -group [get_clocks clk_100m] \
    -group [get_clocks -of_objects [get_pins -hierarchical -filter {NAME =~ *u_clk/*u_mmcm/CLKOUT*}]]
