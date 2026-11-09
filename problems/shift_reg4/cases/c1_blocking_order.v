// expect: blocking_in_seq, sim_mismatch
// 错误：时序块里用阻塞赋值逐位移动。q[0] 先被改成 d，紧接着 q[1] 读到的已经是新值，
// 结果四位全都等于 d
module top_module (
    input  wire       clk,
    input  wire       rst,
    input  wire       d,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst)
            q = 4'b0000;
        else begin
            q[0] = d;
            q[1] = q[0];
            q[2] = q[1];
            q[3] = q[2];
        end
    end
endmodule
