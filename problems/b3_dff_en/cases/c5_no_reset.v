// expect: sim_mismatch
// 错误：没写复位，q 一开始是不确定值 x，第 0 步对不上
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire en,
    input  wire d,
    output reg  q
);
    always @(posedge clk) begin
        if (en) q <= d;
    end
endmodule
