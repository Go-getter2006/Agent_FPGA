// testbench：序列检测器（101）
// 每个 STEP：先给激励，时钟上升沿到来，再在下降沿采样打印
module tb;
    reg  clk = 1'b0;
    reg  rst = 1'b1;
    reg  in  = 1'b0;
    wire out;

    top_module dut (.clk(clk), .rst(rst), .in(in), .out(out));

    always #5 clk = ~clk;

    integer n = 0;

    task step(input r, input i);
        begin
            rst = r;
            in  = i;
            @(negedge clk);
            $display("STEP %0d | rst=%b in=%b | out=%b", n, rst, in, out);
            n = n + 1;
        end
    endtask

    initial begin
        step(1, 0);  // 0  复位
        step(0, 1);  // 1  S1
        step(0, 0);  // 2  S10
        step(0, 1);  // 3  S101，out=1
        step(0, 0);  // 4  S10（重叠）
        step(0, 1);  // 5  S101，out=1
        step(0, 1);  // 6  S1
        step(0, 1);  // 7  S1 保持
        step(0, 0);  // 8  S10
        step(0, 0);  // 9  S0
        step(0, 1);  // 10 S1
        step(0, 0);  // 11 S10
        step(0, 1);  // 12 S101，out=1
        step(0, 1);  // 13 S1
        step(0, 0);  // 14 S10
        step(1, 1);  // 15 复位优先：回到 S0
        step(0, 0);  // 16 S0 保持
        step(0, 1);  // 17 S1
        step(0, 0);  // 18 S10
        step(0, 1);  // 19 S101，out=1
        step(0, 0);  // 20 S10
        step(0, 0);  // 21 S0
        step(0, 1);  // 22 S1
        step(0, 0);  // 23 S10
        step(0, 1);  // 24 S101，out=1
        $finish;
    end
endmodule
