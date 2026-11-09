// testbench：带使能的 D 触发器
// 每个 STEP：先给激励，时钟上升沿到来，再在下降沿采样打印
module tb;
    reg  clk = 1'b0;
    reg  rst = 1'b1;
    reg  en  = 1'b0;
    reg  d   = 1'b0;
    wire q;

    top_module dut (.clk(clk), .rst(rst), .en(en), .d(d), .q(q));

    always #5 clk = ~clk;

    integer n = 0;

    task step(input r, input e, input v);
        begin
            rst = r;
            en  = e;
            d   = v;
            @(negedge clk);
            $display("STEP %0d | rst=%b en=%b d=%b | q=%b", n, rst, en, d, q);
            n = n + 1;
        end
    endtask

    initial begin
        step(1, 0, 0);  // 0  复位
        step(0, 1, 1);  // 1  记下 1
        step(0, 0, 0);  // 2  en=0：d 变了，q 保持
        step(0, 0, 1);  // 3  保持
        step(0, 1, 0);  // 4  记下 0
        step(0, 0, 1);  // 5  保持
        step(0, 1, 1);  // 6  记下 1
        step(1, 1, 1);  // 7  复位优先
        step(0, 1, 1);  // 8  记下 1
        $finish;
    end
endmodule
