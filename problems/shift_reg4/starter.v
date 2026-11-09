// 起始代码：d 从最高位移入，整体右移
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       d,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst)
            q <= 4'b0000;
        else
            q <= {d, q[3:1]};
    end
endmodule
