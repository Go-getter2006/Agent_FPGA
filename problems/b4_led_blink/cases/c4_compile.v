// expect: compile_error
// 错误：led 声明成 wire，却在 always 块里赋值
module top_module (
    input  wire clk,
    input  wire rst,
    output wire led
);
    reg [1:0] cnt;

    always @(posedge clk) begin
        if (rst) begin
            cnt <= 2'd0;
            led <= 1'b0;
        end else begin
            cnt <= cnt + 2'd1;
            if (cnt == 2'd3)
                led <= ~led;
        end
    end
endmodule
