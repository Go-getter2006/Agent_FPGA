// testbench：二选一选择器（组合电路）
// 每个 STEP：改变输入，#1 后采样打印
module tb;
    reg  a   = 1'b0;
    reg  b   = 1'b0;
    reg  sel = 1'b0;
    wire y;

    top_module dut (.a(a), .b(b), .sel(sel), .y(y));

    integer n = 0;

    task step(input x, input z, input s);
        begin
            a = x;
            b = z;
            sel = s;
            #1;
            $display("STEP %0d | a=%b b=%b sel=%b | y=%b", n, a, b, sel, y);
            n = n + 1;
            #9;
        end
    endtask

    initial begin
        step(1, 0, 0);  // 0：sel=0 选 a
        step(1, 0, 1);  // 1：sel=1 选 b
        step(0, 1, 1);  // 2
        step(0, 1, 0);  // 3
        step(1, 1, 1);  // 4
        step(0, 0, 1);  // 5
        step(1, 0, 1);  // 6
        step(0, 1, 0);  // 7
        $finish;
    end
endmodule
