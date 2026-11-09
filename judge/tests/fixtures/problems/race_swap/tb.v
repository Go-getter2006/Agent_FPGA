// race_blocking.v / race_nonblocking.v 共用的 testbench（测试专用题目 race_swap）
module tb;
    reg  clk = 1'b0;
    reg  rst = 1'b1;
    wire y1, y2;

    top_module dut (.clk(clk), .rst(rst), .y1(y1), .y2(y2));

    always #5 clk = ~clk;

    integer n;
    initial begin
        for (n = 0; n < 6; n = n + 1) begin
            rst = (n == 0);
            @(negedge clk);
            $display("STEP %0d | rst=%b | y1=%b y2=%b", n, rst, y1, y2);
        end
        $finish;
    end
endmodule
