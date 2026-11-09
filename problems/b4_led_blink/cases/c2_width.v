// expect: width_mismatch, sim_mismatch
// 错误：想“数满 4 个”，写成了 cnt == 3'd4。两位的 cnt 最大只有 3，永远等不到 4，LED 一直不亮
module top_module (
    input  wire clk,
    input  wire rst,
    output reg  led
);
    reg [1:0] cnt;

    always @(posedge clk) begin
        if (rst) begin
            cnt <= 2'd0;
            led <= 1'b0;
        end else begin
            cnt <= cnt + 2'd1;
            if (cnt == 3'd4)
                led <= ~led;
        end
    end
endmodule
