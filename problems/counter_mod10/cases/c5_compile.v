// expect: compile_error
// 错误：信号名写错了（count 没有声明）
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
            else            q <= count + 4'd1;
        end
    end
endmodule
