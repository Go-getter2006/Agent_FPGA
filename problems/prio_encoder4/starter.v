// 起始代码：读懂它，再预测 pos 和 valid
module top_module (
    input  wire [3:0] in,
    output reg  [1:0] pos,
    output wire       valid
);
    assign valid = |in;

    always @(*) begin
        casez (in)
            4'b1???: pos = 2'd3;
            4'b01??: pos = 2'd2;
            4'b001?: pos = 2'd1;
            default: pos = 2'd0;
        endcase
    end
endmodule
