// expect: latch_inferred, fragile_pass
// 隐患：单独用组合块算“下一个值”，但只在 en 为 1 时赋值，next 生成锁存器。
// 时序块也只在 en 为 1 时才用 next，所以仿真正确
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output reg  [3:0] q
);
    reg [3:0] next;

    always @(*) begin
        if (en)
            next = (q == 4'd9) ? 4'd0 : q + 4'd1;
    end

    always @(posedge clk) begin
        if (rst)     q <= 4'd0;
        else if (en) q <= next;
    end
endmodule
