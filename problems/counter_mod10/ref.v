// 参考答案：模 10 计数器（0–9 循环），同步复位、带使能
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst)
            q <= 4'd0;
        else if (en) begin
            if (q == 4'd9) q <= 4'd0;
            else            q <= q + 4'd1;
        end
        // en 为 0 时不赋值：时序块里没赋值就是保持原值，不会生成锁存器
    end
endmodule
