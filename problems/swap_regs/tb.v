// testbench：两个寄存器互换
// 每个 STEP：先给激励，时钟上升沿到来，再在下降沿采样打印
module tb;
    reg        clk  = 1'b0;
    reg        rst  = 1'b1;
    reg        load = 1'b0;
    reg  [3:0] da   = 4'd0;
    reg  [3:0] db   = 4'd0;
    wire [3:0] x, y;

    top_module dut (.clk(clk), .rst(rst), .load(load), .da(da), .db(db), .x(x), .y(y));

    always #5 clk = ~clk;

    integer n = 0;

    task step(input r, input l, input [3:0] a, input [3:0] b);
        begin
            rst  = r;
            load = l;
            da   = a;
            db   = b;
            @(negedge clk);
            $display("STEP %0d | rst=%b load=%b da=%b db=%b | x=%b y=%b", n, rst, load, da, db, x, y);
            n = n + 1;
        end
    endtask

    initial begin
        step(1, 0, 4'd0,  4'd0);   // 0  复位
        step(0, 1, 4'd3,  4'd5);   // 1  装入 3、5
        step(0, 0, 4'd0,  4'd0);   // 2  互换 → 5、3
        step(0, 0, 4'd0,  4'd0);   // 3  互换 → 3、5
        step(0, 0, 4'd15, 4'd15);  // 4  load 为 0，da、db 不起作用
        step(0, 1, 4'd9,  4'd12);  // 5  装入 9、12
        step(0, 0, 4'd0,  4'd0);   // 6  互换
        step(0, 0, 4'd0,  4'd0);   // 7  互换
        step(1, 1, 4'd7,  4'd7);   // 8  复位优先于装入
        step(0, 1, 4'd1,  4'd2);   // 9  装入 1、2
        step(0, 0, 4'd0,  4'd0);   // 10 互换
        step(0, 1, 4'd6,  4'd6);   // 11 装入相同的值
        step(0, 0, 4'd0,  4'd0);   // 12 互换后不变
        $finish;
    end
endmodule
