module top_module (
    input  wire clk,
    input  wire rst,
    input  wire en,
    input  wire d,
    output reg  q
);
    always @(posedge clk) begin
        if (rst)      q <= ____;   // 复位
        else if (____) q <= ____;  // 使能时记下 d
    end
endmodule
