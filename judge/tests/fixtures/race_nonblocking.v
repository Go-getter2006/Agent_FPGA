// 与 race_blocking.v 结构相同，改用非阻塞赋值：先算好所有右边，再统一更新左边，
// 两个寄存器每个时钟交换一次，与 always 块的先后顺序无关
module top_module (
    input  wire clk,
    input  wire rst,
    output reg  y1,
    output reg  y2
);
    always @(posedge clk) begin
        if (rst) y1 <= 1'b0;
        else     y1 <= y2;
    end

    always @(posedge clk) begin
        if (rst) y2 <= 1'b1;
        else     y2 <= y1;
    end
endmodule
