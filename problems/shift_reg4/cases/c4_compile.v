// expect: compile_error
// 错误：拼接 {} 里两个信号之间漏了逗号
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
            q <= {q[2:0] d};
    end
endmodule
