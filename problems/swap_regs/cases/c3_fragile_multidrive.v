// expect: multi_driven, fragile_pass
// 隐患：复位单独写在第三个 always 块里，x、y 各有两个块在驱动。
// 条件互斥，仿真正确，但硬件里每个寄存器都有两个驱动源
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
        end
    end

    always @(posedge clk) begin
        if (!rst) x <= load ? da : y;
    end

    always @(posedge clk) begin
        if (!rst) y <= load ? db : x;
    end
endmodule
