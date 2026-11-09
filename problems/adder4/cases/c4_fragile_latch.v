// expect: latch_inferred, fragile_pass
// 隐患：用 if / else if 分 cin 为 1 和 0 两种情况，最后没有 else。
// 仿真里 cin 只会是 0 或 1，结果正确；综合工具却认为还有一条路径没赋值，生成锁存器
module top_module (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output reg  [3:0] sum,
    output reg        cout
);
    always @(*) begin
        if (cin == 1'b1)
            {cout, sum} = a + b + 1'b1;
        else if (cin == 1'b0)
            {cout, sum} = a + b;
    end
endmodule
