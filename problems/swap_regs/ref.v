// 参考答案：两个寄存器每拍互换，load 时装入新值，同步复位
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       load,
    input  wire [3:0] da,
    input  wire [3:0] db,
    output reg  [3:0] x,
    output reg  [3:0] y
);
    // 两个块都用非阻塞赋值：同一个时钟沿先读旧值，再统一更新，与块的先后无关
    always @(posedge clk) begin
        if (rst)       x <= 4'd0;
        else if (load) x <= da;
        else           x <= y;
    end

    always @(posedge clk) begin
        if (rst)       y <= 4'd0;
        else if (load) y <= db;
        else           y <= x;
    end
endmodule
