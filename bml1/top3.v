`timescale 1 ns/ 100 ps
`default_nettype none // Strictly enforce all nets to be declared

module top 
(
  input  wire       clk,   
  output wire [3:0] led
);// module top


  wire clk_100m_loc;
  wire clk_100m_tree;
  wire sim_mode;
  reg [3:0] d_flop_sr = 4'd1;
  reg pulse_1hz = 0;
  reg [26:0] ck_div_cnt = 27'd0;
  
  assign clk_100m_loc = clk;
  assign clk_100m_tree = clk_100m_loc;
  
always @( posedge clk_100m_tree ) begin
  if ( pulse_1hz == 1 ) begin
    d_flop_sr[3:0] <= { d_flop_sr[2:0], d_flop_sr[3] };
  end
end
  assign led = d_flop_sr[3:0];

  assign sim_mode = 0;

always @( posedge clk_100m_tree ) begin : proc_ck_div
  if ( ( sim_mode == 1 && ck_div_cnt == 27'd10  ) ||
       ( sim_mode == 0 && ck_div_cnt == 27'd1000000000 ) ) begin
    ck_div_cnt <= 26'd1;
    pulse_1hz  <= 1;
  end else begin
    ck_div_cnt <= ck_div_cnt[26:0] + 1;
    pulse_1hz <= 0;
  end
end


endmodule // top.v
`default_nettype wire // enable Verilog default for any 3rd party IP needing it