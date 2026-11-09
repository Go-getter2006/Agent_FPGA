// expect: sim_mismatch
// 错误：没有计数，每个时钟沿都翻转，LED 闪得太快
module top_module (
    input  wire clk,
    input  wire rst,
    output reg  led
);
    always @(posedge clk) begin
        if (rst) led <= 1'b0;
        else     led <= ~led;
    end
endmodule
