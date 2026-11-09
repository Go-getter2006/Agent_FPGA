// 参考答案：4 位优先编码器，最高位优先
module top_module (
    input  wire [3:0] in,
    output reg  [1:0] pos,
    output wire       valid
);
    // 只要有一位是 1，valid 就为 1
    assign valid = |in;

    // if / else if 自上而下判断，先判断的优先级高
    always @(*) begin
        if (in[3])      pos = 2'd3;
        else if (in[2]) pos = 2'd2;
        else if (in[1]) pos = 2'd1;
        else            pos = 2'd0;
    end
endmodule
