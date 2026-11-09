// expect: sim_mismatch
// 错误：只加了 a + b，忘了 cin
module top_module (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output wire [3:0] sum,
    output wire       cout
);
    assign {cout, sum} = a + b;
endmodule
