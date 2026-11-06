// Monitor tap on an AXI4-Lite link for the ILA debug build (DEBUG_ILA=1).
// The free Vivado licence allows at most 5 probe ports per ILA, so the
// handshake is bundled into one vector:
//   ctl[0] arvalid  [1] arready  [2] rvalid  [3] rready
//   ctl[4] awvalid  [5] awready  [6] wvalid  [7] wready  [8] bvalid  [9] bready
//   ctl[11:10] rresp  [13:12] bresp  [29:14] araddr  [45:30] awaddr
`timescale 1 ns / 1 ps
module axi_tap_lite (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK",
       X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi" *)
    input wire        s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWADDR",
       X_INTERFACE_MODE = "monitor" *)
    input wire [15:0] s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWVALID" *) input wire        s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi AWREADY" *) input wire        s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WDATA"   *) input wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WSTRB"   *) input wire [3:0]  s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WVALID"  *) input wire        s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi WREADY"  *) input wire        s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BRESP"   *) input wire [1:0]  s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BVALID"  *) input wire        s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi BREADY"  *) input wire        s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARADDR"  *) input wire [15:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARVALID" *) input wire        s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi ARREADY" *) input wire        s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RDATA"   *) input wire [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RRESP"   *) input wire [1:0]  s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RVALID"  *) input wire        s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 s_axi RREADY"  *) input wire        s_axi_rready,

    output wire [45:0] ctl,
    output wire [31:0] rdata,
    output wire [31:0] wdata
);
    assign ctl = {s_axi_awaddr, s_axi_araddr, s_axi_bresp, s_axi_rresp,
                  s_axi_bready, s_axi_bvalid, s_axi_wready, s_axi_wvalid, s_axi_awready, s_axi_awvalid,
                  s_axi_rready, s_axi_rvalid, s_axi_arready, s_axi_arvalid};
    assign rdata = s_axi_rdata;
    assign wdata = s_axi_wdata;
endmodule
