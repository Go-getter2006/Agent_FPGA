// 参考答案：LED 每 4 个时钟周期翻转一次（计数分频）
module top_module (
    input  wire clk,
    input  wire rst,
    output reg  led
);
    // 计数器：0、1、2、3、0、1……两位刚好数到 3。
    // 真实板子的时钟是 50 MHz，要把 3 换成 24_999_999（计数器也要加宽到 25 位），LED 才会每 0.5 秒翻转一次
    reg [1:0] cnt;

    always @(posedge clk) begin
        if (rst) begin
            cnt <= 2'd0;
            led <= 1'b0;
        end else begin
            cnt <= cnt + 2'd1;              // 两位计数，3 之后自然回到 0
            if (cnt == 2'd3)
                led <= ~led;                // 数满一轮，LED 翻转
        end
    end
endmodule
