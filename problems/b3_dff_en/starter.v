// 起始代码：带使能的 D 触发器（这道是预测题，代码是对的，先读懂它）
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire en,
    input  wire d,
    output reg  q
);
    // 只在时钟上升沿这一瞬间更新；其余时间 q 保持不变，这就是“记忆”
    always @(posedge clk) begin
        if (rst)     q <= 1'b0;   // 复位优先：清零
        else if (en) q <= d;      // 使能：记下 d
        // 都不满足：什么也不写，q 保持原值（时序逻辑里这是正常的，不会生成锁存器）
    end
endmodule
