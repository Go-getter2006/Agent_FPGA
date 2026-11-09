// 时序块用 =、组合块用 <=。单个时序块里只有一条赋值，仿真碰巧正确
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire in,
    output wire out
);
    localparam S0 = 2'd0, S1 = 2'd1, S10 = 2'd2, S101 = 2'd3;
    reg [1:0] state, next_state;

    always @(posedge clk) begin
        if (rst) state = S0;
        else     state = next_state;
    end

    assign out = (state == S101);

    always @(*) begin
        case (state)
            S0:      next_state <= in ? S1   : S0;
            S1:      next_state <= in ? S1   : S10;
            S10:     next_state <= in ? S101 : S0;
            S101:    next_state <= in ? S1   : S10;
            default: next_state <= S0;
        endcase
    end
endmodule
