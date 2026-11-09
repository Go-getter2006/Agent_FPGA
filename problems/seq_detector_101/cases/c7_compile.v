// expect: compile_error
// 错误：out 声明为 wire（默认类型），却在 always 块里赋值
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire in,
    output      out
);
    localparam S0 = 2'd0, S1 = 2'd1, S10 = 2'd2, S101 = 2'd3;
    reg [1:0] state, next_state;

    always @(posedge clk) begin
        if (rst) state <= S0;
        else     state <= next_state;
    end

    always @(*) begin
        out = (state == S101);
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
