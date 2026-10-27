// Block-design face of the CAN core: an AXI4-Lite slave (which the block
// design maps into BAR1 automatically) bridged to the core's APB4 port.
// Instantiates the VHDL wrapper can_wrap, which instantiates the core from
// library ctu_can_fd_rtl. One transaction at a time; writes take priority.
`timescale 1 ns / 1 ps
`default_nettype none

module can_wrap_bd (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK",
       X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET s_axi_aresetn" *)
    input  wire        s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST",
       X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        s_axi_aresetn,

    input  wire [15:0] s_axi_awaddr,
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output wire        s_axi_wready,
    output wire [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [15:0] s_axi_araddr,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready,

    input  wire [63:0] timestamp,
    (* X_INTERFACE_INFO = "xilinx.com:signal:interrupt:1.0 irq INTERRUPT",
       X_INTERFACE_PARAMETER = "SENSITIVITY LEVEL_HIGH" *)
    output wire        irq,
    output wire        can_tx,
    input  wire        can_rx
);
    localparam IDLE = 2'd0, SETUP = 2'd1, ACCESS = 2'd2, RESP = 2'd3;
    reg [1:0]  state = IDLE;
    reg        aw_got = 1'b0, w_got = 1'b0;
    reg [15:0] awaddr_l = 16'd0;
    reg [31:0] wdata_l = 32'd0;
    reg [3:0]  wstrb_l = 4'd0;
    reg        is_write = 1'b0;
    reg [15:0] addr = 16'd0;
    reg        psel = 1'b0, penable = 1'b0;

    wire        pready, pslverr;
    wire [31:0] prdata;

    assign s_axi_awready = (state == IDLE) && !aw_got;
    assign s_axi_wready  = (state == IDLE) && !w_got;
    assign s_axi_arready = (state == IDLE) && !aw_got && !w_got && !s_axi_awvalid && !s_axi_wvalid;
    assign s_axi_bresp   = 2'b00;
    assign s_axi_rresp   = 2'b00;

    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            state <= IDLE; aw_got <= 1'b0; w_got <= 1'b0;
            psel <= 1'b0; penable <= 1'b0;
            s_axi_bvalid <= 1'b0; s_axi_rvalid <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    if (s_axi_awvalid && !aw_got) begin awaddr_l <= s_axi_awaddr; aw_got <= 1'b1; end
                    if (s_axi_wvalid && !w_got) begin wdata_l <= s_axi_wdata; wstrb_l <= s_axi_wstrb; w_got <= 1'b1; end
                    if (aw_got && w_got) begin
                        is_write <= 1'b1; addr <= awaddr_l;
                        aw_got <= 1'b0; w_got <= 1'b0;
                        psel <= 1'b1; state <= SETUP;
                    end else if (s_axi_arvalid && s_axi_arready) begin
                        is_write <= 1'b0; addr <= s_axi_araddr;
                        psel <= 1'b1; state <= SETUP;
                    end
                end
                SETUP: begin
                    penable <= 1'b1; state <= ACCESS;
                end
                ACCESS: begin
                    if (pready) begin
                        psel <= 1'b0; penable <= 1'b0;
                        if (is_write) s_axi_bvalid <= 1'b1;
                        else begin s_axi_rdata <= prdata; s_axi_rvalid <= 1'b1; end
                        state <= RESP;
                    end
                end
                RESP: begin
                    if (s_axi_bvalid && s_axi_bready) begin s_axi_bvalid <= 1'b0; state <= IDLE; end
                    if (s_axi_rvalid && s_axi_rready) begin s_axi_rvalid <= 1'b0; state <= IDLE; end
                end
            endcase
        end
    end

    can_wrap core (
        .aclk          (s_axi_aclk),
        .arstn         (s_axi_aresetn),
        .s_apb_paddr   ({16'd0, addr}),
        .s_apb_psel    (psel),
        .s_apb_penable (penable),
        .s_apb_pwrite  (is_write),
        .s_apb_pwdata  (wdata_l),
        .s_apb_pstrb   (is_write ? wstrb_l : 4'b0000),
        .s_apb_pprot   (3'b000),
        .s_apb_pready  (pready),
        .s_apb_prdata  (prdata),
        .s_apb_pslverr (pslverr),
        .timestamp     (timestamp),
        .irq           (irq),
        .can_tx        (can_tx),
        .can_rx        (can_rx)
    );
endmodule

`default_nettype wire
