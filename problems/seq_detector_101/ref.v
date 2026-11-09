// 参考答案：序列检测器（101），Moore 型，允许重叠，同步复位（高有效）
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire in,
    output wire out
);
    // 状态以“已经看到的有用后缀”命名
    localparam S0   = 2'd0;  // 什么都没匹配上
    localparam S1   = 2'd1;  // 已看到 1
    localparam S10  = 2'd2;  // 已看到 10
    localparam S101 = 2'd3;  // 已看到 101（输出 1）

    reg [1:0] state, next_state;

    // 状态寄存器
    always @(posedge clk) begin
        if (rst) state <= S0;
        else     state <= next_state;
    end

    // 输出只由当前状态决定（Moore 型）
    assign out = (state == S101);

    // 次态逻辑
    always @(*) begin
        case (state)
            S0:      next_state = in ? S1   : S0;
            S1:      next_state = in ? S1   : S10;
            S10:     next_state = in ? S101 : S0;
            S101:    next_state = in ? S1   : S10;
            default: next_state = S0;
        endcase
    end
endmodule
