# Out-of-tree build of the ctucanfd driver (kernel v7.0 sources) with hardware
# timestamp support for the LiteFury CAN FD card. Build on the host:
#   make -C /lib/modules/$(uname -r)/build M=$PWD modules
# then (as root) unload the in-tree modules and insmod ctucanfd.ko,
# ctucanfd_pci.ko from here. See ../hwts-load.sh.
obj-m += ctucanfd.o
ctucanfd-y := ctucanfd_base.o
obj-m += ctucanfd_pci.o
