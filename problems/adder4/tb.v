// testbench：4 位加法器（组合电路）
// 每个 STEP：改变输入，#1 后采样打印
module tb;
    reg  [3:0] a   = 4'd0;
    reg  [3:0] b   = 4'd0;
    reg        cin = 1'b0;
    wire [3:0] sum;
    wire       cout;

    top_module dut (.a(a), .b(b), .cin(cin), .sum(sum), .cout(cout));

    integer n = 0;

    task step(input [3:0] x, input [3:0] y, input c);
        begin
            a = x;
            b = y;
            cin = c;
            #1;
            $display("STEP %0d | a=%b b=%b cin=%b | sum=%b cout=%b", n, a, b, cin, sum, cout);
            n = n + 1;
            #9;
        end
    endtask

    initial begin
        step(4'd0,  4'd0,  1'b0);  // 0
        step(4'd3,  4'd4,  1'b0);  // 7
        step(4'd5,  4'd3,  1'b1);  // 9：用到 cin
        step(4'd0,  4'd0,  1'b1);  // 1：只有 cin
        step(4'd7,  4'd8,  1'b0);  // 15：不进位的最大值
        step(4'd8,  4'd8,  1'b0);  // 16：进位
        step(4'd15, 4'd1,  1'b0);  // 16：进位
        step(4'd9,  4'd6,  1'b1);  // 16：cin 引起进位
        step(4'd12, 4'd3,  1'b0);  // 15
        step(4'd12, 4'd3,  1'b1);  // 16：同样的 a、b，cin 决定是否进位
        step(4'd10, 4'd11, 1'b0);  // 21
        step(4'd6,  4'd9,  1'b0);  // 15
        step(4'd14, 4'd1,  1'b1);  // 16
        step(4'd15, 4'd0,  1'b1);  // 16
        step(4'd15, 4'd15, 1'b0);  // 30
        step(4'd15, 4'd15, 1'b1);  // 31：最大值
        $finish;
    end
endmodule
