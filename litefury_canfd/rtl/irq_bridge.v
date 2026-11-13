// Turns the CAN cores' level interrupts into requests for the AXI PCIe
// bridge's INTX_MSI_Request/Grant handshake. All cores share the one
// interrupt (the driver registers it IRQF_SHARED once per core).
//
//   MSI mode (msi_enable = 1, what Linux normally negotiates):
//     one MSI per rising edge of any core's irq (an edge that arrives while a
//     request is waiting for its grant is remembered), and another every
//     ~1 ms while any irq stays high, so a missed edge can never leave the
//     driver waiting forever.
//   Legacy INTx mode (msi_enable = 0):
//     the bridge sends Assert_INTx / Deassert_INTx alternately on successive
//     requests, so a request is issued on every edge of the OR of the irqs.
//
// irq_in and irq_enable come from the CAN clock domain and are synchronised.
`timescale 1 ns / 1 ps
`default_nettype none

module irq_bridge #(
    parameter NUM_IRQ = 1
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK",
       X_INTERFACE_PARAMETER = "ASSOCIATED_RESET resetn" *)
    input  wire       clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST",
       X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire       resetn,
    input  wire [NUM_IRQ-1:0] irq_in,
    input  wire       irq_enable,
    input  wire       msi_enable,
    input  wire       grant,
    output reg        req,
    output wire [4:0] msi_vector_num
);
    assign msi_vector_num = 5'd0;

    (* ASYNC_REG = "TRUE" *) reg [NUM_IRQ-1:0] irq_s0 = {NUM_IRQ{1'b0}}, irq_s1 = {NUM_IRQ{1'b0}};
    (* ASYNC_REG = "TRUE" *) reg [1:0] en_s  = 2'b00;
    always @(posedge clk) begin
        irq_s0 <= irq_in;
        irq_s1 <= irq_s0;
        en_s   <= {en_s[0],  irq_enable};
    end
    wire [NUM_IRQ-1:0] irqs = irq_s1 & {NUM_IRQ{en_s[1]}};
    wire irq  = |irqs;

    reg [NUM_IRQ-1:0] irqs_d = {NUM_IRQ{1'b0}};
    wire rise = |(irqs & ~irqs_d);
    reg        pend    = 1'b0;    // a rising edge seen while a request was outstanding
    reg        irq_d   = 1'b0;
    reg [16:0] retrig  = 17'd0;   // 2^17 cycles, about 1 ms at 125 MHz

    always @(posedge clk) begin
        if (!resetn) begin
            req    <= 1'b0;
            irq_d  <= 1'b0;
            irqs_d <= {NUM_IRQ{1'b0}};
            pend   <= 1'b0;
            retrig <= 17'd0;
        end else begin
            irq_d  <= irq;
            irqs_d <= irqs;
            retrig <= irq ? retrig + 17'd1 : 17'd0;
            if (req) begin
                if (grant)
                    req <= 1'b0;
                if (rise)
                    pend <= 1'b1;
            end else if (msi_enable) begin
                pend <= 1'b0;
                if (rise || pend || (irq && (&retrig)))
                    req <= 1'b1;
            end else begin
                pend <= 1'b0;
                if (irq ^ irq_d)
                    req <= 1'b1;
            end
        end
    end
endmodule

`default_nettype wire
