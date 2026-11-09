// 竞争的经典例子：两个 always 块在同一个时钟沿用阻塞赋值互相读写。
// 真实硬件里两个寄存器应当交换数值；仿真结果却取决于仿真器先执行哪个块
module top_module (
    input  wire clk,
    input  wire rst,
    output reg  y1,
    output reg  y2
);
    always @(posedge clk) begin
        if (rst) y1 = 1'b0;
        else     y1 = y2;
    end

    always @(posedge clk) begin
        if (rst) y2 = 1'b1;
        else     y2 = y1;
    end
endmodule
