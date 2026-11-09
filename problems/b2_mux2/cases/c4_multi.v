// expect: multi_driven, sim_mismatch
// 错误：新写了选择器，但起始代码那一行没删，y 有两个驱动
module top_module (
    input  wire a,
    input  wire b,
    input  wire sel,
    output wire y
);
    assign y = a;
    assign y = sel ? b : a;
endmodule
