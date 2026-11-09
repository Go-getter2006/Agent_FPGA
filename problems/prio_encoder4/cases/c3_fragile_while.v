// expect: non_synthesizable, fragile_pass
// 隐患：按 C 语言的思路用 while 循环从高位往下找。仿真结果正确，
// 但循环次数取决于输入，综合工具无法把它变成固定的电路
module top_module (
    input  wire [3:0] in,
    output reg  [1:0] pos,
    output wire       valid
);
    integer i;

    assign valid = |in;

    always @(*) begin
        i = 3;
        while (i > 0 && in[i] == 1'b0)
            i = i - 1;
        pos = i[1:0];
    end
endmodule
