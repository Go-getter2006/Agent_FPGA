// expect: blocking_in_seq, sim_mismatch
// 错误：时序块里用了 =，cnt 先加 1 再被比较，LED 早一拍翻转
module top_module (
    input  wire clk,
    input  wire rst,
    output reg  led
);
    reg [1:0] cnt;

    always @(posedge clk) begin
        if (rst) begin
            cnt = 2'd0;
            led = 1'b0;
        end else begin
            cnt = cnt + 2'd1;
            if (cnt == 2'd3)
                led = ~led;
        end
    end
endmodule
