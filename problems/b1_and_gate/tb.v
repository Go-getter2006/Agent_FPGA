// testbench：与门（组合电路）
// 每个 STEP：改变输入，#1 后采样打印
module tb;
    reg  a = 1'b0;
    reg  b = 1'b0;
    wire y;

    top_module dut (.a(a), .b(b), .y(y));

    integer n = 0;

    task step(input x, input z);
        begin
            a = x;
            b = z;
            #1;
            $display("STEP %0d | a=%b b=%b | y=%b", n, a, b, y);
            n = n + 1;
            #9;
        end
    endtask

    initial begin
        step(0, 0);  // 0
        step(0, 1);  // 1
        step(1, 0);  // 2
        step(1, 1);  // 3：只有这时 y = 1
        step(0, 0);  // 4
        step(1, 1);  // 5
        step(1, 0);  // 6
        step(0, 1);  // 7
        $finish;
    end
endmodule
