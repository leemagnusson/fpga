create_clock -period 10.000 -name clk_100m -waveform {0.000 5.000} [get_ports clk]
set_input_jitter clk_100m 0.200

# The line input is asynchronous and goes through a synchroniser; switches
# and buttons are static or debounced; the outputs are pulses with no
# reference clock at the receiving instrument.
set_false_path -from [get_ports {ja1_rx sw[*] btn*}]
set_false_path -to   [get_ports {led[*] seg[*] dp an[*] ja2_trig0 ja3_trig1 ja4_trig2 ja7_trig3 ja8_de ja9_txd ja10_carrier}]
