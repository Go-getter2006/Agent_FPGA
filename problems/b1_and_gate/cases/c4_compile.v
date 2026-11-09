// expect: compile_error
// 错误：y 声明成了 reg，却用 assign 连续赋值
module top_module (
    input  wire a,
    input  wire b,
    output reg  y
);
    assign y = a & b;
endmodule
