// expect: multi_driven, fragile_pass
// 隐患：复位写在另一个 always 块里，两个块都驱动 led 和 cnt。
// 仿真里两个块不会在同一个时钟沿同时写，结果正确；但真实电路里一根线不能有两个驱动
module top_module (
    input  wire clk,
    input  wire rst,
    output reg  led
);
    reg [1:0] cnt;

    always @(posedge clk)
        if (rst) begin
            cnt <= 2'd0;
            led <= 1'b0;
        end

    always @(posedge clk)
        if (!rst) begin
            cnt <= cnt + 2'd1;
            if (cnt == 2'd3)
                led <= ~led;
        end
endmodule
