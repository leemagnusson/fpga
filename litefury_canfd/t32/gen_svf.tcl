# Write "erase, program and verify <file> in the card's W25Q128JV" as an SVF
# file, for JTAG probes that Vivado cannot drive itself (see jtag.sh).
#
#   vivado -mode batch -source gen_svf.tcl -tclargs <file.bin|file.mcs> <out.svf> [<fpga part> [<flash part>]]
#
# A .bin goes to flash address 0. The SVF first loads Vivado's JTAG-to-SPI
# bridge into the FPGA, so the design stops running while it plays.
lassign $argv file svf part flash
if {$part eq ""}  { set part xc7a50t }
if {$flash eq ""} { set flash w25q128jvq-spi-x1_x2_x4 }
open_hw_manager
connect_hw_server
create_hw_target svf_target
open_hw_target [get_hw_targets -regexp .*svf_target]
set dev [create_hw_device -part $part]
current_hw_device $dev
create_hw_cfgmem -hw_device $dev -mem_dev [lindex [get_cfgmem_parts $flash] 0]
set cfg [get_property PROGRAM.HW_CFGMEM $dev]
set_property PROGRAM.ADDRESS_RANGE {use_file} $cfg
set_property PROGRAM.FILES [list $file] $cfg
set_property PROGRAM.PRM_FILE {} $cfg
set_property PROGRAM.UNUSED_PIN_TERMINATION {pull-none} $cfg
set_property PROGRAM.BLANK_CHECK 0 $cfg
set_property PROGRAM.ERASE 1 $cfg
set_property PROGRAM.CFG_PROGRAM 1 $cfg
set_property PROGRAM.VERIFY 1 $cfg
set_property PROGRAM.CHECKSUM 0 $cfg
create_hw_bitstream -hw_device $dev [get_property PROGRAM.HW_CFGMEM_BITFILE $dev]
program_hw_devices $dev
program_hw_cfgmem -hw_cfgmem $cfg
write_hw_svf -force $svf
close_hw_target
exit
