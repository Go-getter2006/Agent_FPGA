// 参考答案：与门。y 只有在 a 和 b 都是 1 时才是 1
module top_module (
    input  wire a,
    input  wire b,
    output wire y
);
    // assign 描述一根一直接通的导线：a、b 一变，y 立刻跟着变
    assign y = a & b;
endmodule
