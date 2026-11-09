module top_module (
    input  wire clk,
    input  wire rst,
    input  wire in,
    output wire out
);
    localparam S0 = 2'd0, S1 = 2'd1, S10 = 2'd2, S101 = 2'd3;   // 按“已经看到的后缀”命名
    reg [1:0] state, next_state;

    always @(posedge clk)          // 状态寄存器：时钟沿更新
        if (rst) state <= ____;
        else     state <= ____;

    always @(*) begin              // 次态逻辑：组合逻辑，用 =
        case (state)
            S0:      next_state = in ? ____ : ____;
            S1:      next_state = in ? ____ : ____;
            S10:     next_state = in ? ____ : ____;
            S101:    next_state = in ? ____ : ____;
            default: next_state = S0;
        endcase
    end

    assign out = ____;             // Moore 型：输出只看当前状态
endmodule
