// expect: width_mismatch, sim_mismatch
// 错误：以为右移 4 位就能取出进位。但这个表达式只按 4 位计算，
// 进位在加法时就已经丢了，cout 恒为 0
module top_module (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output wire [3:0] sum,
    output wire       cout
);
    assign sum  = a + b + cin;
    assign cout = (a + b + cin) >> 4;
endmodule
