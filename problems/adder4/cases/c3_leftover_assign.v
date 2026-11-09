// expect: multi_driven, sim_mismatch
// 错误：新写了带进位的赋值，但起始代码里的两句没删，sum、cout 各有两个驱动
module top_module (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output wire [3:0] sum,
    output wire       cout
);
    assign sum  = a + b;
    assign cout = 1'b0;
    assign {cout, sum} = a + b + cin;
endmodule
