// expect: latch_inferred, fragile_pass
// 隐患：写成了组合 always 块，en 为 0 时 q 没有赋值，综合出来是锁存器而不是触发器，也不再等时钟沿。
// 这个 testbench 只在每个周期采样一次，看不出差别；“硬件”页里触发器个数会变成 0
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire en,
    input  wire d,
    output reg  q
);
    always @(*) begin
        if (rst)     q = 1'b0;
        else if (en) q = d;
    end
endmodule
