# Build the 10BASE-T1S trigger monitor for the Basys 3 (non-project flow,
# like bml1/*). Run with ./go.sh or: ../ci/vivado.sh -mode batch -source go.tcl
set design_name top
set device xc7a35tcpg236-1
set_part $device

source top_rtl_list.tcl

read_xdc ./constraints/${design_name}_timing.xdc
synth_design -top $design_name -part $device
read_xdc ./constraints/${design_name}_physical.xdc
opt_design
place_design
route_design
write_checkpoint -force routed_design

set rep_dir ./reports
file mkdir $rep_dir
check_timing             -file $rep_dir/post_route_timing_check.rpt
report_timing_summary    -file $rep_dir/post_route_timing_summary.rpt
report_clock_utilization -file $rep_dir/post_route_clock_util.rpt
report_utilization       -file $rep_dir/post_route_util.rpt
report_io                -file $rep_dir/post_route_io.rpt

write_bitstream -force -bin_file ${design_name}.bit

# Skip board programming when running under CI (no hardware attached)
if {![info exists ::env(CI)]} {
    source program.tcl
}
exit
