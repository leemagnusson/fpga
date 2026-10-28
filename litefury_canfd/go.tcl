# Build the LiteFury CAN FD card bitstream (project mode, scripted).
#
#   vivado -mode batch -source go.tcl          # or ./go.sh, or ../ci/vivado.sh ...
#
# Environment overrides:
#   CTU_CAN_FD_SRC  path to the CTU CAN FD core's src/ directory
#                   (default: ../third_party/CTU-CAN-FD/src, a git submodule)
#   PCI_VENDOR_ID / PCI_DEVICE_ID   PCI IDs (default 0x1760 / 0xFF00, the IDs the
#                   mainline ctucanfd_pci driver binds to; see README.md)
#   VIVADO_JOBS     parallel jobs for synthesis/implementation (default 4)
#   CI              if set, skip programming the board at the end
#
# Outputs, named like the other projects in this repo so CI treats them alike:
#   top.bit, top.bin, reports/

set design_name top
set device xc7a100tfgg484-2L
set here [file dirname [file normalize [info script]]]
set repo [file normalize $here/..]

proc env_or {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} { return $::env($name) }
    return $default
}
set ::pci_vendor_id [env_or PCI_VENDOR_ID 0x1760]
set ::pci_device_id [env_or PCI_DEVICE_ID 0xFF00]
set can_src [env_or CTU_CAN_FD_SRC $repo/third_party/CTU-CAN-FD/src]
set jobs    [env_or VIVADO_JOBS 4]

if {![file exists $can_src/slf_rtl.yml] && ![info exists ::env(BD_SMOKE_TEST)]} {
    error "CTU CAN FD core not found at $can_src. Fetch the submodule:\n  git submodule update --init\nor set CTU_CAN_FD_SRC."
}

file delete -force ./build
create_project -force canfd ./build -part $device
set_property target_language VHDL [current_project]
add_files [list $here/rtl/misc_regs.vhd $here/rtl/irq_bridge.v]
if {[file exists $can_src/slf_rtl.yml]} {
    # Core RTL, in the order of the core's own file list, into its library.
    set fh [open $can_src/slf_rtl.yml r]
    set can_files {}
    foreach line [split [read $fh] "\n"] {
        if {[regexp {^\s*-\s*file:\s*(\S+)} $line -> f]} { lappend can_files $can_src/$f }
    }
    close $fh
    add_files $can_files
    set_property library ctu_can_fd_rtl [get_files $can_files]
    add_files [list $here/rtl/can_wrap.vhd $here/rtl/can_wrap_bd.v]
}
update_compile_order -fileset sources_1

source $here/bd.tcl

set wrapper [make_wrapper -files [get_files canfd.bd] -top]
# Vivado copies its environment banner into the wrapper's header comment; on a
# machine with a multi-line /etc/os-release value that breaks the VHDL. Keep
# only the code (from the first "library" line on).
set fh [open $wrapper r]; set lines [split [read $fh] "\n"]; close $fh
set start [lsearch -regexp $lines {^\s*library\s}]
if {$start > 0} {
    set fh [open $wrapper w]
    puts $fh [join [lrange $lines $start end] "\n"]
    close $fh
}
add_files -norecurse $wrapper
set_property top canfd_wrapper [current_fileset]
update_compile_order -fileset sources_1

add_files -fileset constrs_1 [list \
    $here/constraints/litefury_early.xdc \
    $here/constraints/litefury.xdc \
    $here/constraints/litefury_impl.xdc]
set_property PROCESSING_ORDER EARLY [get_files litefury_early.xdc]
set_property PROCESSING_ORDER LATE  [get_files litefury.xdc]
set_property PROCESSING_ORDER LATE  [get_files litefury_impl.xdc]
set_property USED_IN {implementation} [get_files litefury_impl.xdc]

generate_target all [get_files canfd.bd]
# The PCIe bridge is tight at 125 MHz on the -2L speed grade; physical
# optimisation closes it.
set_property strategy Performance_ExplorePostRoutePhysOpt [get_runs impl_1]
# (set after the strategy, which resets step arguments)
set_property STEPS.WRITE_BITSTREAM.ARGS.BIN_FILE true [get_runs impl_1]

launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "synthesis failed" }

launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "implementation failed" }

open_run impl_1
set rep_dir ./reports
file mkdir $rep_dir
check_timing            -file $rep_dir/post_route_timing_check.rpt
report_timing_summary   -file $rep_dir/post_route_timing_summary.rpt
report_clock_utilization -file $rep_dir/post_route_clock_util.rpt
report_clock_interaction -file $rep_dir/post_route_clock_interaction.rpt
report_utilization      -file $rep_dir/post_route_util.rpt
report_io               -file $rep_dir/post_route_io.rpt
# Record where the PCIe lanes landed, to catch a silently ignored LOC.
set fh [open $rep_dir/gt_placement.txt w]
foreach c [get_cells -hierarchical -regexp {.*gtp_channel\.gtpe2_channel_i}] {
    puts $fh "[get_property LOC $c]  $c"
}
close $fh

file copy -force ./build/canfd.runs/impl_1/canfd_wrapper.bit ./${design_name}.bit
file copy -force ./build/canfd.runs/impl_1/canfd_wrapper.bin ./${design_name}.bin
puts "Bitstream: [file normalize ./${design_name}.bit]"

# Skip board programming when running under CI (no hardware attached)
if {![info exists ::env(CI)]} {
    source $here/program.tcl
}
exit
