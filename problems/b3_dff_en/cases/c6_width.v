// expect: width_mismatch, sim_mismatch
// 错误：复位值写成了 2 位的 2'b10，赋给 1 位的 q 时高位被截掉；同时忘了使能
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire en,
    input  wire d,
    output reg  q
);
    always @(posedge clk) begin
        if (rst) q <= 2'b11;
        else     q <= d;
    end
endmodule
