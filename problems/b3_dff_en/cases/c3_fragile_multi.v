// expect: multi_driven, fragile_pass
// 隐患：复位和使能写在两个 always 块里，两个块都驱动 q。
// 仿真里两个块不会在同一个时钟沿同时写，结果正确；但真实电路里一根线不能有两个驱动
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire en,
    input  wire d,
    output reg  q
);
    always @(posedge clk)
        if (rst) q <= 1'b0;

    always @(posedge clk)
        if (!rst && en) q <= d;
endmodule
