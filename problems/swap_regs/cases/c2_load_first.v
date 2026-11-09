// expect: sim_mismatch
// 错误：先判断 load、后判断 rst，复位不再是最高优先级
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       load,
    input  wire [3:0] da,
    input  wire [3:0] db,
    output reg  [3:0] x,
    output reg  [3:0] y
);
    always @(posedge clk) begin
        if (load)     x <= da;
        else if (rst) x <= 4'd0;
        else          x <= y;
    end

    always @(posedge clk) begin
        if (load)     y <= db;
        else if (rst) y <= 4'd0;
        else          y <= x;
    end
endmodule
