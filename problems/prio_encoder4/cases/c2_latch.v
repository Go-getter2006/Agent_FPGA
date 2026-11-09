// expect: latch_inferred, sim_mismatch
// 错误：最后没有 else，in 全为 0 时 pos 没被赋值，生成锁存器
module top_module (
    input  wire [3:0] in,
    output reg  [1:0] pos,
    output wire       valid
);
    assign valid = |in;

    always @(*) begin
        if (in[3])      pos = 2'd3;
        else if (in[2]) pos = 2'd2;
        else if (in[1]) pos = 2'd1;
        else if (in[0]) pos = 2'd0;
    end
endmodule
