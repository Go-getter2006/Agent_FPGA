// 起始代码：与门（这道是预测题，代码是对的，先读懂它）
module top_module (
    input  wire a,
    input  wire b,
    output wire y
);
    // assign 描述一根一直接通的导线：a、b 一变，y 立刻跟着变
    assign y = a & b;
endmodule
