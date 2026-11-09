// expect: sim_mismatch
// 错误：只改了一半，d 仍然从最高位进入（等于没改起始代码的方向），只是改写成了移位运算
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
            q <= (q >> 1) | {d, 3'b000};
    end
endmodule
