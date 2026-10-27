// Turns the CAN core's level interrupt into requests for the AXI PCIe
// bridge's INTX_MSI_Request/Grant handshake.
//
//   MSI mode (msi_enable = 1, what Linux normally negotiates):
//     one MSI per rising edge of irq, and another every ~1 ms while irq stays
//     high, so a missed edge can never leave the driver waiting forever.
//   Legacy INTx mode (msi_enable = 0):
//     the bridge sends Assert_INTx / Deassert_INTx alternately on successive
//     requests, so a request is issued on every edge of irq.
//
// irq_in and irq_enable come from the CAN clock domain and are synchronised.
`timescale 1 ns / 1 ps
`default_nettype none

module irq_bridge (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK",
       X_INTERFACE_PARAMETER = "ASSOCIATED_RESET resetn" *)
    input  wire       clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST",
       X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire       resetn,
    input  wire       irq_in,
    input  wire       irq_enable,
    input  wire       msi_enable,
    input  wire       grant,
    output reg        req,
    output wire [4:0] msi_vector_num
);
    assign msi_vector_num = 5'd0;

    (* ASYNC_REG = "TRUE" *) reg [1:0] irq_s = 2'b00;
    (* ASYNC_REG = "TRUE" *) reg [1:0] en_s  = 2'b00;
    always @(posedge clk) begin
        irq_s <= {irq_s[0], irq_in};
        en_s  <= {en_s[0],  irq_enable};
    end
    wire irq = irq_s[1] & en_s[1];

    reg        irq_d   = 1'b0;
    reg [16:0] retrig  = 17'd0;   // 2^17 cycles, about 1 ms at 125 MHz

    always @(posedge clk) begin
        if (!resetn) begin
            req    <= 1'b0;
            irq_d  <= 1'b0;
            retrig <= 17'd0;
        end else begin
            irq_d  <= irq;
            retrig <= irq ? retrig + 17'd1 : 17'd0;
            if (req) begin
                if (grant)
                    req <= 1'b0;
            end else if (msi_enable) begin
                if ((irq & ~irq_d) || (irq && (&retrig)))
                    req <= 1'b1;
            end else begin
                if (irq ^ irq_d)
                    req <= 1'b1;
            end
        end
    end
endmodule

`default_nettype wire
