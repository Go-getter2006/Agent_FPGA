// expect: compile_error
// 错误：语句末尾少了分号
module top_module (
    input  wire a,
    input  wire b,
    input  wire sel,
    output wire y
);
    assign y = sel ? b : a
endmodule
