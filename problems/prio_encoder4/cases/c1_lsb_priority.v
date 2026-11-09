// expect: sim_mismatch
// 错误：判断顺序反了，变成最低位优先
module top_module (
    input  wire [3:0] in,
    output reg  [1:0] pos,
    output wire       valid
);
    assign valid = |in;

    always @(*) begin
        if (in[0])      pos = 2'd0;
        else if (in[1]) pos = 2'd1;
        else if (in[2]) pos = 2'd2;
        else if (in[3]) pos = 2'd3;
        else            pos = 2'd0;
    end
endmodule
