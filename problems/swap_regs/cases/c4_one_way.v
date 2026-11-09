// expect: sim_mismatch
// 错误：只写了 x 取 y，忘了 y 取 x，y 永远保持装入的值
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
        if (rst) begin
            x <= 4'd0;
            y <= 4'd0;
        end else if (load) begin
            x <= da;
            y <= db;
        end else begin
            x <= y;
        end
    end
endmodule
