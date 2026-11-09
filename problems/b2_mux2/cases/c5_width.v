// expect: width_mismatch, sim_mismatch
// 错误：以为拼接就能“选”出一位，{a, b} 是 2 位，赋给 1 位的 y 时只留下了 b
module top_module (
    input  wire a,
    input  wire b,
    input  wire sel,
    output wire y
);
    assign y = sel ? b : {a, b};
endmodule
