// expect: compile_error
// 错误：q 声明成 wire，却在 always 块里赋值（always 里赋值的信号要声明成 reg）
module top_module (
    input  wire clk,
    input  wire rst,
    input  wire en,
    input  wire d,
    output wire q
);
    always @(posedge clk) begin
        if (rst)     q <= 1'b0;
        else if (en) q <= d;
    end
endmodule
