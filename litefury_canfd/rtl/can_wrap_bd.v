// Block-design face of the CAN core: an AXI4-Lite slave (which the block
// design maps into BAR1 automatically) bridged to the core's APB4 port.
// Instantiates the VHDL wrapper can_wrap, which instantiates the core from
// library ctu_can_fd_rtl. One transaction at a time; writes take priority.
//
// TX timestamp capture block (not part of the CTU core), decoded locally at
// BAR1 offsets 0x1000-0x1FFF (the core's own registers end well below that):
//   0x1000  TSCAP_ID    read-only, 0x54534C46 ("TSLF")
//   0x1004  TSCAP_RATE  read-only, timestamp counter frequency in Hz
//   0x1008  TSCAP_NBUF  read-only, number of TXT buffer timestamp latches
//   0x1010 + 8*i  TXTB_i timestamp low word  (i = 0..NBUF-1)
//   0x1014 + 8*i  TXTB_i timestamp high word
// The 64-bit timestamp is sampled on the core's SOF pulse (the same pulse
// and clock edge the core's RX buffer uses when RX_SETTINGS.RTSOP selects
// SOF capture, so TX and RX stamps share one reference point) and copied
// into latch i on the tx_done pulse of a frame transmitted from TXT buffer
// i. A frame that loses arbitration gets a fresh SOF sample on its retry.
// A latch only changes on that buffer's next successful transmission, so the
// driver can read the two words non-atomically while the buffer is in TX_OK.
// Writes in this range are accepted and ignored.
`timescale 1 ns / 1 ps
`default_nettype none

module can_wrap_bd #(
    parameter TS_RATE_HZ = 32'd80_000_000,   // must match the clock feeding misc_regs' counter
    parameter TXT_BUFS   = 4
) (
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

    // ---- TX timestamp latches -------------------------------------------
    wire        tx_done, sof;
    wire [2:0]  tx_done_txtb;
    reg  [63:0] sof_ts = 64'd0;
    reg  [63:0] tx_ts [0:TXT_BUFS-1];
    integer     k;
    initial for (k = 0; k < TXT_BUFS; k = k + 1) tx_ts[k] = 64'd0;

    always @(posedge s_axi_aclk) begin
        if (sof)
            sof_ts <= timestamp;
        if (tx_done && tx_done_txtb < TXT_BUFS)
            tx_ts[tx_done_txtb] <= sof_ts;
    end

    // Local (non-core) register window: 0x1000-0x1FFF.
    wire        local_sel = (addr[15:12] == 4'h1);
    wire [8:0]  local_q   = addr[11:3];          // 8-byte slot: 0x1010 -> slot 2
    wire [2:0]  local_buf = local_q[2:0] - 3'd2; // slot 2 -> buffer 0
    reg  [31:0] local_rdata;
    always @(*) begin
        local_rdata = 32'd0;
        case (addr[11:2])
            10'h000: local_rdata = 32'h54534C46;
            10'h001: local_rdata = TS_RATE_HZ;
            10'h002: local_rdata = TXT_BUFS;
            default:
                if (local_q >= 9'd2 && local_q < 9'd2 + TXT_BUFS)
                    local_rdata = addr[2] ? tx_ts[local_buf][63:32] : tx_ts[local_buf][31:0];
        endcase
    end

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
                        psel <= (awaddr_l[15:12] != 4'h1); state <= SETUP;
                    end else if (s_axi_arvalid && s_axi_arready) begin
                        is_write <= 1'b0; addr <= s_axi_araddr;
                        psel <= (s_axi_araddr[15:12] != 4'h1); state <= SETUP;
                    end
                end
                SETUP: begin
                    if (local_sel) begin
                        if (is_write) s_axi_bvalid <= 1'b1;
                        else begin s_axi_rdata <= local_rdata; s_axi_rvalid <= 1'b1; end
                        state <= RESP;
                    end else begin
                        penable <= 1'b1; state <= ACCESS;
                    end
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
        .tx_done       (tx_done),
        .tx_done_txtb  (tx_done_txtb),
        .sof           (sof),
        .irq           (irq),
        .can_tx        (can_tx),
        .can_rx        (can_rx)
    );
endmodule

`default_nettype wire
