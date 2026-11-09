// testbench：4 位移位寄存器
// 每个 STEP：先给激励，时钟上升沿到来，再在下降沿采样打印
module tb;
    reg        clk = 1'b0;
    reg        rst = 1'b1;
    reg        d   = 1'b0;
    wire [3:0] q;

    top_module dut (.clk(clk), .rst(rst), .d(d), .q(q));

    always #5 clk = ~clk;

    integer n = 0;

    task step(input r, input i);
        begin
            rst = r;
            d   = i;
            @(negedge clk);
            $display("STEP %0d | rst=%b d=%b | q=%b", n, rst, d, q);
            n = n + 1;
        end
    endtask

    initial begin
        step(1, 0);  // 0  复位
        step(0, 1);  // 1  0001
        step(0, 0);  // 2  0010
        step(0, 1);  // 3  0101
        step(0, 1);  // 4  1011
        step(0, 0);  // 5  0110
        step(0, 0);  // 6  1100
        step(0, 1);  // 7  1001
        step(0, 0);  // 8  0010
        step(0, 0);  // 9  0100
        step(0, 0);  // 10 1000
        step(0, 0);  // 11 0000：最早移入的 1 被移出
        step(0, 1);  // 12 0001
        step(0, 1);  // 13 0011
        step(1, 1);  // 14 复位优先
        step(0, 1);  // 15 0001
        step(0, 1);  // 16 0011
        step(0, 1);  // 17 0111
        step(0, 1);  // 18 1111
        step(0, 0);  // 19 1110
        $finish;
    end
endmodule
