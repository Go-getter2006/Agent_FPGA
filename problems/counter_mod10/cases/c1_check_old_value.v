// expect: sim_mismatch
// 错误：先写 q <= q + 1，再判断 q == 10。非阻塞赋值要到块结束后才更新，
// 判断时读到的还是旧值，于是 q 会出现 10，变成模 11
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst)
            q <= 4'd0;
        else if (en) begin
            q <= q + 4'd1;
            if (q == 4'd10) q <= 4'd0;
        end
    end
endmodule
