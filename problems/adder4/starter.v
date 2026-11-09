// 起始代码：不带进位的 4 位加法器（cin 没用上，cout 恒为 0）
module top_module (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output wire [3:0] sum,
    output wire       cout
);
    assign sum  = a + b;
    assign cout = 1'b0;
endmodule
