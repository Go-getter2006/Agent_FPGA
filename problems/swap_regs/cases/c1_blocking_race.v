// expect: blocking_in_seq, sim_mismatch
// 错误：两个块都用阻塞赋值。先执行的块改完 x，后执行的块读到的已经是新值，
// 结果两个寄存器变成同一个数，而且结果取决于哪个块先执行
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
        if (rst)       x = 4'd0;
        else if (load) x = da;
        else           x = y;
    end

    always @(posedge clk) begin
        if (rst)       y = 4'd0;
        else if (load) y = db;
        else           y = x;
    end
endmodule
