// expect: width_mismatch, sim_mismatch
// 错误：把 pos 当成独热码写成 4 位常数，赋给 2 位的 pos 时高位被截掉
module top_module (
    input  wire [3:0] in,
    output reg  [1:0] pos,
    output wire       valid
);
    assign valid = |in;

    always @(*) begin
        if (in[3])      pos = 4'b1000;
        else if (in[2]) pos = 4'b0100;
        else if (in[1]) pos = 4'b0010;
        else            pos = 4'b0001;
    end
endmodule
