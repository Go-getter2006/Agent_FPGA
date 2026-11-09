// expect: sim_mismatch
// 错误：把与写成了或，a、b 有一个是 1 就输出 1
module top_module (
    input  wire a,
    input  wire b,
    output wire y
);
    assign y = a | b;
endmodule
