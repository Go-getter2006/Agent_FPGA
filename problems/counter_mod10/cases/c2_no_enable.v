// expect: sim_mismatch
// 错误：没有处理 en，每个时钟都在计数
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst)
            q <= 4'd0;
        else if (q == 4'd9)
            q <= 4'd0;
        else
            q <= q + 4'd1;
    end
endmodule
