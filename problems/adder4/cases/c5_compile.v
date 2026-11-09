// expect: compile_error
// 错误：sum、cout 声明成了 reg，却用 assign 连续赋值
module top_module (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output reg  [3:0] sum,
    output reg        cout
);
    assign {cout, sum} = a + b + cin;
endmodule
