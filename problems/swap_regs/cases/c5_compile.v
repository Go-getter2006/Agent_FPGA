// expect: compile_error
// 错误：always 后面的事件控制漏了 @
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       load,
    input  wire [3:0] da,
    input  wire [3:0] db,
    output reg  [3:0] x,
    output reg  [3:0] y
);
    always (posedge clk) begin
        if (rst)       x <= 4'd0;
        else if (load) x <= da;
        else           x <= y;
    end

    always @(posedge clk) begin
        if (rst)       y <= 4'd0;
        else if (load) y <= db;
        else           y <= x;
    end
endmodule
