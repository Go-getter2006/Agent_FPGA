// expect: width_mismatch, sim_mismatch
// 错误：内部计数寄存器只有 3 位，最大只能到 7，永远等不到 9
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output wire [3:0] q
);
    reg [2:0] cnt;

    always @(posedge clk) begin
        if (rst)
            cnt <= 3'd0;
        else if (en) begin
            if (cnt == 4'd9) cnt <= 3'd0;
            else             cnt <= cnt + 3'd1;
        end
    end

    assign q = cnt;
endmodule
