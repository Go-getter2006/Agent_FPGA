module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst)
            q <= ____;                 // 复位
        else if (____) begin           // 使能时才计数
            if (q == ____) q <= ____;  // 数到 9 之后回到 0
            else           q <= ____;  // 否则加 1
        end
    end
endmodule
