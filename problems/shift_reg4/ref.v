// 参考答案：4 位移位寄存器（串入并出），d 从最低位移入，同步复位
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
            q <= {q[2:0], d};   // 整体左移一位，d 进入 q[0]
    end
endmodule
