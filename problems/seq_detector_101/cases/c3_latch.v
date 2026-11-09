// expect: latch_inferred, sim_mismatch
// 错误：S10 分支漏写 else，也没有 default，next_state 生成锁存器
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire in,
    output wire out
);
    localparam S0 = 2'd0, S1 = 2'd1, S10 = 2'd2, S101 = 2'd3;
    reg [1:0] state, next_state;

    always @(posedge clk) begin
        if (rst) state <= S0;
        else     state <= next_state;
    end

    assign out = (state == S101);

    always @(*) begin
        case (state)
            S0:   next_state = in ? S1 : S0;
            S1:   next_state = in ? S1 : S10;
            S10:  if (in) next_state = S101;
            S101: next_state = in ? S1 : S10;
        endcase
    end
endmodule
