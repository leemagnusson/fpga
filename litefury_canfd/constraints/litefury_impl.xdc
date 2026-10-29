# Implementation-only constraints (USED_IN implementation): the clocks named
# here are created inside the PCIe IP and do not exist during synthesis.

## The 80 MHz CAN domain (from sys_clk) and the PCIe-derived AXI clock are
## unrelated; the SmartConnect clock converter and the synchronisers in
## irq_bridge/misc_regs handle the crossings.
set_clock_groups -asynchronous \
    -group [get_clocks -include_generated_clocks -of_objects [get_ports sys_clk_clk_p]] \
    -group [get_clocks -include_generated_clocks txoutclk]
