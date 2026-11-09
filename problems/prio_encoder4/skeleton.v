module top_module (
    input  wire [3:0] in,
    output reg  [1:0] pos,
    output wire       valid
);
    assign valid = ____;          // 只要有一位是 1

    always @(*) begin             // 先判断的优先级高
        if (in[3])      pos = ____;
        else if (____)  pos = ____;
        else if (____)  pos = ____;
        else            pos = ____;   // 最后一定要有 else
    end
endmodule
