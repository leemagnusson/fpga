# Load top.bit into the LiteFury over JTAG (volatile; lost at power cycle).
# For PCIe the host must see the card at boot, so for real use write the
# flash instead: see program_flash.tcl.
open_hw_manager
connect_hw_server -allow_non_jtag
open_hw_target
set dev [lindex [get_hw_devices xc7a100t_0] 0]
current_hw_device $dev
set_property PROBES.FILE {} $dev
set_property FULL_PROBES.FILE {} $dev
set_property PROGRAM.FILE {top.bit} $dev
program_hw_devices $dev
refresh_hw_device $dev
