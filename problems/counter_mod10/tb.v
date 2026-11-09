// testbench：模 10 计数器
// 每个 STEP：先给激励，时钟上升沿到来，再在下降沿采样打印
module tb;
    reg        clk = 1'b0;
    reg        rst = 1'b1;
    reg        en  = 1'b0;
    wire [3:0] q;

    top_module dut (.clk(clk), .rst(rst), .en(en), .q(q));

    always #5 clk = ~clk;

    integer n = 0;
    integer k;

    task step(input r, input e);
        begin
            rst = r;
            en  = e;
            @(negedge clk);
            $display("STEP %0d | rst=%b en=%b | q=%b", n, rst, en, q);
            n = n + 1;
        end
    endtask

    initial begin
        step(1, 0);                          // 0      复位
        for (k = 0; k < 12; k = k + 1)
            step(0, 1);                      // 1–12   1..9、0、1、2（第 10 步回到 0）
        step(0, 0);                          // 13     保持 2
        step(0, 0);                          // 14     保持 2
        step(0, 1);                          // 15     3
        step(1, 1);                          // 16     复位优先于使能
        for (k = 0; k < 9; k = k + 1)
            step(0, 1);                      // 17–25  1..9
        step(0, 0);                          // 26     在 9 上保持
        step(0, 1);                          // 27     9 之后回到 0
        step(0, 1);                          // 28     1
        $finish;
    end
endmodule
