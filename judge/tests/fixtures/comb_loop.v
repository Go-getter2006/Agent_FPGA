// 组合环路：in 为 1 时 a = ~a 无延时振荡，仿真停不下来，用来测超时
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire in,
    output wire out
);
    wire a;
    assign a = in ? ~a : 1'b0;
    assign out = a;
endmodule
