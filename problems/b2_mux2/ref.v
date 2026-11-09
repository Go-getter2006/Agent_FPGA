// 参考答案：二选一选择器。sel 像一个开关，决定把 a 还是 b 接到输出
module top_module (
    input  wire a,
    input  wire b,
    input  wire sel,
    output wire y
);
    // 条件运算符：sel 为 1 取冒号前面的 b，为 0 取冒号后面的 a。
    // 它综合出来就是一个“二选一”的开关电路，不是 if 语句那样先判断再执行
    assign y = sel ? b : a;
endmodule
