`timescale 1 ns/ 100 ps
`default_nettype none // Strictly enforce all nets to be declared

module top 
(
  input  wire       clk,   
  output wire [3:0] led
);// module top


  wire clk_100m_loc;
  wire clk_100m_tree;
  reg [3:0] d_flop_sr = 4'd1;
  
  assign clk_100m_loc = clk;
  assign clk_100m_tree = clk_100m_loc;
  
always @( posedge clk_100m_tree ) begin
  d_flop_sr[3:0] <= { d_flop_sr[2:0], d_flop_sr[3] };
end
  assign led = d_flop_sr[3:0];


endmodule // top.v
`default_nettype wire // enable Verilog default for any 3rd party IP needing it