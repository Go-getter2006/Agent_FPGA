// expect: sim_mismatch
// 错误：把 a、b 的位置写反了，sel = 0 时反而输出 b
module top_module (
    input  wire a,
    input  wire b,
    input  wire sel,
    output wire y
);
    assign y = sel ? a : b;
endmodule
