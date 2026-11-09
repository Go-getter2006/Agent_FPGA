// testbench：4 位优先编码器（组合电路）
// 每个 STEP：改变输入，#1 后采样打印
module tb;
    reg  [3:0] in = 4'b0000;
    wire [1:0] pos;
    wire       valid;

    top_module dut (.in(in), .pos(pos), .valid(valid));

    integer k;
    initial begin
        // 穷举 16 种输入
        for (k = 0; k < 16; k = k + 1) begin
            in = k;
            #1;
            $display("STEP %0d | in=%b | pos=%b valid=%b", k, in, pos, valid);
            #9;
        end
        $finish;
    end
endmodule
