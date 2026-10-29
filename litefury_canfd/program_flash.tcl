# Write top.bin to the LiteFury's configuration flash so the card configures
# itself at power-up (required for PCIe enumeration).
#
#   vivado -mode batch -source program_flash.tcl
#
# LiteFury boards ship with either a 128 Mbit or a 256 Mbit S25FL flash; set
# FLASH_PART accordingly (default 256 Mbit). Afterwards power-cycle the host
# (a warm reboot is not enough for the card to re-enumerate reliably).
set flash_part [expr {[info exists ::env(FLASH_PART)] ? $::env(FLASH_PART) : "s25fl256sxxxxxx0-spi-x1_x2_x4"}]

open_hw_manager
connect_hw_server -allow_non_jtag
open_hw_target
set dev [lindex [get_hw_devices xc7a100t_0] 0]
current_hw_device $dev
refresh_hw_device -update_hw_probes false $dev
create_hw_cfgmem -hw_device $dev [lindex [get_cfgmem_parts $flash_part] 0]
set cfg [get_property PROGRAM.HW_CFGMEM $dev]
set_property PROGRAM.BLANK_CHECK 0 $cfg
set_property PROGRAM.ERASE 1 $cfg
set_property PROGRAM.CFG_PROGRAM 1 $cfg
set_property PROGRAM.VERIFY 1 $cfg
set_property PROGRAM.CHECKSUM 0 $cfg
set_property PROGRAM.ADDRESS_RANGE {use_file} $cfg
set_property PROGRAM.FILES [list top.bin] $cfg
set_property PROGRAM.PRM_FILE {} $cfg
set_property PROGRAM.UNUSED_PIN_TERMINATION {pull-none} $cfg
create_hw_bitstream -hw_device $dev [get_property PROGRAM.HW_CFGMEM_BITFILE $dev]
program_hw_devices $dev
program_hw_cfgmem -hw_cfgmem $cfg
exit
