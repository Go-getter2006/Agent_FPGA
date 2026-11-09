// expect: multi_driven, fragile_pass
// 隐患：两个 always 块分别写 q 的不同部分，但复位时第一个块清零了全部 4 位，
// 于是 q[3:1] 在两个块里都被赋值。两块的条件互斥，仿真正确，硬件里却有两个驱动源
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       d,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst) q <= 4'b0000;
        else     q[0] <= d;
    end

    always @(posedge clk) begin
        if (!rst) q[3:1] <= q[2:0];
    end
endmodule
