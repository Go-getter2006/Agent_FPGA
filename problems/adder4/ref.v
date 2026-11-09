// 参考答案：4 位加法器，带进位输入和进位输出
module top_module (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output wire [3:0] sum,
    output wire       cout
);
    // 左边拼成 5 位，右边的加法就按 5 位计算，最高位的进位不会丢
    assign {cout, sum} = a + b + cin;
endmodule
