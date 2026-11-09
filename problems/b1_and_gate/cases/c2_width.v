// expect: width_mismatch, sim_mismatch
// 错误：把两个输入拼在一起赋给 1 位的 y，高位被截掉，y 实际上等于 b
module top_module (
    input  wire a,
    input  wire b,
    output wire y
);
    assign y = {a, b};
endmodule
