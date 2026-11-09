// expect: multi_driven, sim_mismatch
// 错误：两条 assign 同时驱动 y，相当于两个电路抢一根线
module top_module (
    input  wire a,
    input  wire b,
    output wire y
);
    assign y = a & b;
    assign y = a;
endmodule
