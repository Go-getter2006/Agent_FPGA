// expect: width_mismatch, sim_mismatch
// 错误：state、next_state 忘了写位宽，只有 1 位，存不下 4 个状态
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire in,
    output wire out
);
    localparam S0 = 2'd0, S1 = 2'd1, S10 = 2'd2, S101 = 2'd3;
    reg state, next_state;

    always @(posedge clk) begin
        if (rst) state <= S0;
        else     state <= next_state;
    end

    assign out = (state == S101);

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
