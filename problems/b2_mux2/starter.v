// 起始代码：选择器还没接上开关，y 永远等于 a（sel 没有用上）
module top_module (
    input  wire a,
    input  wire b,
    input  wire sel,
    output wire y
);
    // 修改这一行：让 sel 决定输出 a 还是 b
    assign y = a;
endmodule
