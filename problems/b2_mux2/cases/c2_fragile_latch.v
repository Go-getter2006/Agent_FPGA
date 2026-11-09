// expect: latch_inferred, fragile_pass
// 隐患：if / else if 分两种情况，最后没有 else。仿真里 sel 只会是 0 或 1，结果正确；
// 综合工具却认为还有一条路径没给 y 赋值，生成锁存器
module top_module (
    input  wire a,
    input  wire b,
    input  wire sel,
    output reg  y
);
    always @(*) begin
        if (sel == 1'b1)
            y = b;
        else if (sel == 1'b0)
            y = a;
    end
endmodule
