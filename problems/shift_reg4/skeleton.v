module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       d,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst)
            q <= ____;
        else
            q <= {____, ____};    // 拼接：原来的低 3 位往高处挪一位，d 补在最低位
    end
endmodule
