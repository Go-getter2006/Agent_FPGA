// expect: latch_inferred, fragile_pass
// 隐患：out 用 if / else if 写，最后没有 else。四个状态都列到了，仿真正确，
// 但综合工具看到的是“有一条路径没给 out 赋值”，于是生成锁存器
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire in,
    output reg  out
);
    localparam S0 = 2'd0, S1 = 2'd1, S10 = 2'd2, S101 = 2'd3;
    reg [1:0] state, next_state;

    always @(posedge clk) begin
        if (rst) state <= S0;
        else     state <= next_state;
    end

    always @(*) begin
        if (state == S101)
            out = 1'b1;
        else if (state == S0 || state == S1 || state == S10)
            out = 1'b0;
    end

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
