// expect: sim_mismatch
// 错误：没写复位，cnt 和 led 一开始都是不确定值 x，永远算不出确定的结果
module top_module (
    input  wire clk,
    input  wire rst,
    output reg  led
);
    reg [1:0] cnt;

    always @(posedge clk) begin
        cnt <= cnt + 2'd1;
        if (cnt == 2'd3)
            led <= ~led;
    end
endmodule
