// expect: latch_inferred, fragile_pass
// 隐患：按 C 语言的习惯用 if / else if 写，最后没有 else。
// 仿真结果正确，但综合工具认为还有一条路径没给 y 赋值，生成锁存器
module top_module (
    input  wire a,
    input  wire b,
    output reg  y
);
    always @(*) begin
        if (a == 1'b1 && b == 1'b1)
            y = 1'b1;
        else if (a == 1'b0 || b == 1'b0)
            y = 1'b0;
    end
endmodule
