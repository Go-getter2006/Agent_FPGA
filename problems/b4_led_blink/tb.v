// testbench：LED 计数分频
// 每个 STEP：先给激励，时钟上升沿到来，再在下降沿采样打印
module tb;
    reg  clk = 1'b0;
    reg  rst = 1'b1;
    wire led;

    top_module dut (.clk(clk), .rst(rst), .led(led));

    always #5 clk = ~clk;

    integer n = 0;
    integer k;

    task step(input r);
        begin
            rst = r;
            @(negedge clk);
            $display("STEP %0d | rst=%b | led=%b", n, rst, led);
            n = n + 1;
        end
    endtask

    initial begin
        step(1);                     // 0      复位：led = 0
        for (k = 0; k < 13; k = k + 1)
            step(0);                 // 1–13   第 4、8、12 步翻转
        step(1);                     // 14     再次复位
        for (k = 0; k < 5; k = k + 1)
            step(0);                 // 15–19  第 18 步翻转
        $finish;
    end
endmodule
