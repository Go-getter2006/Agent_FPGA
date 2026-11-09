module top_module (
    input  wire clk,
    input  wire rst,
    output reg  led
);
    reg [1:0] cnt;                 // 内部计数器：0–3

    always @(posedge clk) begin
        if (rst) begin
            cnt <= ____;
            led <= ____;
        end else begin
            cnt <= ____;           // 每个时钟沿加 1
            if (____)              // 数满一轮的时候
                led <= ____;       // 翻转
        end
    end
endmodule
