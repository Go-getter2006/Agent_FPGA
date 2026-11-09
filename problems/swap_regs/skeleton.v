module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       load,
    input  wire [3:0] da,
    input  wire [3:0] db,
    output reg  [3:0] x,
    output reg  [3:0] y
);
    always @(posedge clk) begin   // 两个块都用 <=：同一个时钟沿先读旧值，再一起更新
        if (rst)       x <= ____;
        else if (load) x <= ____;
        else           x <= ____;
    end

    always @(posedge clk) begin
        if (rst)       y <= ____;
        else if (load) y <= ____;
        else           y <= ____;
    end
endmodule
