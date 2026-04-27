`timescale 1ns/10ps
module GSIM ( clk, reset, in_en, b_in, out_valid, x_out);
input   clk ;
input   reset ;
input   in_en;
output  out_valid;
input   [15:0]  b_in;
output  [31:0]  x_out;

//localparameter
    parameter ITER = 65;

//wire & reg
    //PE
    reg  signed [31:0] x_old_bus[0:3], x1_bus[0:3], x2_bus[0:3], x3_bus[0:3], x4_bus[0:3], x5_bus[0:3], x6_bus[0:3];
    reg  signed [15:0] b_int_bus[0:3];
    wire signed [31:0] x_new_bus[0:3];


    //state registers
    reg [1:0] state_w, state_r;

    //counter
    reg [$clog2(ITER):0] iter_cnt_w, iter_cnt_r;
    reg [3:0] index_cnt_w, index_cnt_r;

    //data registers
    reg [15:0] b_r [0:15], b_w [0:15];
    reg [31:0] x_r [0:15], x_w [0:15];

    //output registers
    reg out_valid_w, out_valid_r;
    reg [31:0] x_out_w, x_out_r;

//FSM
    localparam S_IDLE = 2'd0;
    localparam S_INPUT = 2'd1;
    localparam S_PROC = 2'd2;
    localparam S_OUTPUT = 2'd3;

    //Combinational logic
    always @(*) begin
        state_w = state_r;
        case (state_r)
            S_IDLE: begin
                if (in_en) 
                    state_w = S_INPUT;
            end
            S_INPUT: begin
                if (!in_en) 
                    state_w = S_PROC;
            end
            S_PROC: begin
                if ((iter_cnt_r == ITER - 1) && (index_cnt_r == 4'd3))
                    state_w = S_OUTPUT;
            end
            S_OUTPUT: begin
                if (index_cnt_r == 4'd15)
                    state_w = S_IDLE;
            end
        endcase
    end

    //Sequential logic
    always @(posedge clk or posedge reset) begin
        if (reset) begin
            state_r <= 2'b0;
        end
        else begin
            state_r <= state_w;
        end
    end

//===================== Combinational Part =====================

    //counter
    always @(*) begin
        iter_cnt_w  = iter_cnt_r;
        index_cnt_w = index_cnt_r;
        case (state_r)
            S_IDLE: begin
                if (in_en) 
                    index_cnt_w = 4'd1;
            end
            S_INPUT: begin
                if (in_en) 
                    index_cnt_w = index_cnt_r + 4'd1;
            end
            S_PROC: begin
                if (index_cnt_r == 4'd3) begin
                    index_cnt_w = 4'd0;
                    if (iter_cnt_r == ITER - 1)
                        iter_cnt_w = 0;
                    else
                        iter_cnt_w = iter_cnt_r + 1'b1;
                end else begin
                    index_cnt_w = index_cnt_r + 4'd1;
                end
            end
            S_OUTPUT: begin
                if (index_cnt_r == 4'd15)
                    index_cnt_w = 4'd0;
                else
                    index_cnt_w = index_cnt_r + 4'd1;
            end
        endcase
    end

    //b
    integer i;
    always @(*) begin
        for (i = 0; i < 16; i = i + 1) begin
            b_w[i] = b_r[i];
        end
        if (in_en) begin
            b_w[index_cnt_r] = b_in;
        end
    end

    //PE
    genvar g;
    generate
        for (g = 0; g < 4; g = g + 1) begin : PE_INST
            SOR_PE U (
                .x_old(x_old_bus[g]), .bi_int(b_int_bus[g]),
                .x1(x1_bus[g]), .x2(x2_bus[g]),
                .x3(x3_bus[g]), .x4(x4_bus[g]),
                .x5(x5_bus[g]), .x6(x6_bus[g]),
                .x_new(x_new_bus[g])
            );
        end
    endgenerate

    always @(*) begin
        for (i = 0; i < 4; i = i + 1) begin
            x_old_bus[i] = 0; b_int_bus[i] = 0;
            x1_bus[i] = 0; x2_bus[i] = 0; x3_bus[i] = 0; x4_bus[i] = 0; x5_bus[i] = 0; x6_bus[i] = 0;
        end
        if (state_r == S_PROC) begin
            case (index_cnt_r[1:0])
                2'd0: begin
                    // PE0: x[0], PE1: x[4], PE2: x[8], PE3: x[12]
                    x_old_bus[0] = x_r[0];  b_int_bus[0] = b_r[0];  x1_bus[0] = x_r[1];  x2_bus[0] = 0;       x3_bus[0] = x_r[2];  x4_bus[0] = 0;       x5_bus[0] = x_r[3];  x6_bus[0] = 0;
                    x_old_bus[1] = x_r[4];  b_int_bus[1] = b_r[4];  x1_bus[1] = x_r[5];  x2_bus[1] = x_r[3];  x3_bus[1] = x_r[6];  x4_bus[1] = x_r[2];  x5_bus[1] = x_r[7];  x6_bus[1] = x_r[1];
                    x_old_bus[2] = x_r[8];  b_int_bus[2] = b_r[8];  x1_bus[2] = x_r[9];  x2_bus[2] = x_r[7];  x3_bus[2] = x_r[10]; x4_bus[2] = x_r[6];  x5_bus[2] = x_r[11]; x6_bus[2] = x_r[5];
                    x_old_bus[3] = x_r[12]; b_int_bus[3] = b_r[12]; x1_bus[3] = x_r[13]; x2_bus[3] = x_r[11]; x3_bus[3] = x_r[14]; x4_bus[3] = x_r[10]; x5_bus[3] = x_r[15]; x6_bus[3] = x_r[9];
                end
                2'd1: begin
                    x_old_bus[0] = x_r[1];  b_int_bus[0] = b_r[1];  x1_bus[0] = x_r[2];  x2_bus[0] = x_r[0];  x3_bus[0] = x_r[3];  x4_bus[0] = 0;       x5_bus[0] = x_r[4];  x6_bus[0] = 0;
                    x_old_bus[1] = x_r[5];  b_int_bus[1] = b_r[5];  x1_bus[1] = x_r[6];  x2_bus[1] = x_r[4];  x3_bus[1] = x_r[7];  x4_bus[1] = x_r[3];  x5_bus[1] = x_r[8];  x6_bus[1] = x_r[2];
                    x_old_bus[2] = x_r[9];  b_int_bus[2] = b_r[9];  x1_bus[2] = x_r[10]; x2_bus[2] = x_r[8];  x3_bus[2] = x_r[11]; x4_bus[2] = x_r[7];  x5_bus[2] = x_r[12]; x6_bus[2] = x_r[6];
                    x_old_bus[3] = x_r[13]; b_int_bus[3] = b_r[13]; x1_bus[3] = x_r[14]; x2_bus[3] = x_r[12]; x3_bus[3] = x_r[15]; x4_bus[3] = x_r[11]; x5_bus[3] = 0;       x6_bus[3] = x_r[10];
                end
                2'd2: begin
                    x_old_bus[0] = x_r[2];  b_int_bus[0] = b_r[2];  x1_bus[0] = x_r[3];  x2_bus[0] = x_r[1];  x3_bus[0] = x_r[4];  x4_bus[0] = x_r[0];  x5_bus[0] = x_r[5];  x6_bus[0] = 0;
                    x_old_bus[1] = x_r[6];  b_int_bus[1] = b_r[6];  x1_bus[1] = x_r[7];  x2_bus[1] = x_r[5];  x3_bus[1] = x_r[8];  x4_bus[1] = x_r[4];  x5_bus[1] = x_r[9];  x6_bus[1] = x_r[3];
                    x_old_bus[2] = x_r[10]; b_int_bus[2] = b_r[10]; x1_bus[2] = x_r[11]; x2_bus[2] = x_r[9];  x3_bus[2] = x_r[12]; x4_bus[2] = x_r[8];  x5_bus[2] = x_r[13]; x6_bus[2] = x_r[7];
                    x_old_bus[3] = x_r[14]; b_int_bus[3] = b_r[14]; x1_bus[3] = x_r[15]; x2_bus[3] = x_r[13]; x3_bus[3] = 0;       x4_bus[3] = x_r[12]; x5_bus[3] = 0;       x6_bus[3] = x_r[11];
                end
                2'd3: begin
                    x_old_bus[0] = x_r[3];  b_int_bus[0] = b_r[3];  x1_bus[0] = x_r[4];  x2_bus[0] = x_r[2];  x3_bus[0] = x_r[5];  x4_bus[0] = x_r[1];  x5_bus[0] = x_r[6];  x6_bus[0] = x_r[0];
                    x_old_bus[1] = x_r[7];  b_int_bus[1] = b_r[7];  x1_bus[1] = x_r[8];  x2_bus[1] = x_r[6];  x3_bus[1] = x_r[9];  x4_bus[1] = x_r[5];  x5_bus[1] = x_r[10]; x6_bus[1] = x_r[4];
                    x_old_bus[2] = x_r[11]; b_int_bus[2] = b_r[11]; x1_bus[2] = x_r[12]; x2_bus[2] = x_r[10]; x3_bus[2] = x_r[13]; x4_bus[2] = x_r[9];  x5_bus[2] = x_r[14]; x6_bus[2] = x_r[8];
                    x_old_bus[3] = x_r[15]; b_int_bus[3] = b_r[15]; x1_bus[3] = 0;       x2_bus[3] = x_r[14]; x3_bus[3] = 0;       x4_bus[3] = x_r[13]; x5_bus[3] = 0;       x6_bus[3] = x_r[12];
                end
            endcase
        end
    end

    //x
    integer j;
    always @(*) begin
        for (j = 0; j < 16; j = j + 1) begin
            x_w[j] = x_r[j];
        end
        if (state_r == S_PROC) begin
            case (index_cnt_r[1:0])
                2'd0: begin
                    x_w[0]  = x_new_bus[0];
                    x_w[4]  = x_new_bus[1];
                    x_w[8]  = x_new_bus[2];
                    x_w[12] = x_new_bus[3];
                end
                2'd1: begin
                    x_w[1]  = x_new_bus[0];
                    x_w[5]  = x_new_bus[1];
                    x_w[9]  = x_new_bus[2];
                    x_w[13] = x_new_bus[3];
                end
                2'd2: begin
                    x_w[2]  = x_new_bus[0];
                    x_w[6]  = x_new_bus[1];
                    x_w[10] = x_new_bus[2];
                    x_w[14] = x_new_bus[3];
                end
                2'd3: begin
                    x_w[3]  = x_new_bus[0];
                    x_w[7]  = x_new_bus[1];
                    x_w[11] = x_new_bus[2];
                    x_w[15] = x_new_bus[3];
                end
            endcase
        end
    end

    //Output
    always @(*) begin
        out_valid_w = out_valid_r;
        x_out_w = x_out_r;
        if (state_r == S_OUTPUT) begin
            out_valid_w = 1'b1;
            x_out_w     = x_r[index_cnt_r];
        end
    end

    assign out_valid = out_valid_r;
    assign x_out     = x_out_r;

// ==================== Sequential Part ========================
    always @(posedge clk or posedge reset) begin
        if (reset) begin
            iter_cnt_r  <= 0;
            index_cnt_r <= 0;
            for (i = 0; i < 16; i = i + 1) begin
                b_r[i] <= 16'd0;
                x_r[i] <= 32'd0;
            end
            out_valid_r  <= 1'b0;
            x_out_r      <= 32'd0;
        end else begin
            iter_cnt_r  <= iter_cnt_w;
            index_cnt_r <= index_cnt_w;
            for (i = 0; i < 16; i = i + 1) begin
                b_r[i] <= b_w[i];
                x_r[i] <= x_w[i];
            end
            out_valid_r  <= out_valid_w;
            x_out_r      <= x_out_w;
        end
    end
endmodule

module SOR_PE (
    input  signed [31:0] x_old,
    input  signed [15:0] bi_int,
    input  signed [31:0] x1, x2,
    input  signed [31:0] x3, x4, 
    input  signed [31:0] x5, x6,
    output signed [31:0] x_new
);
    wire signed [32:0] sum_p13 = x1 + x2;
    wire signed [32:0] sum_m6  = x3 + x4;
    wire signed [32:0] sum_p1  = x5 + x6;

    wire signed [35:0] mul_13 = $signed({sum_p13, 3'd0}) + $signed({sum_p13, 2'd0}) + sum_p13;
    wire signed [35:0] mul_6  = $signed({sum_m6, 2'd0}) + $signed({sum_m6, 1'd0});

    wire signed [37:0] tree_stage1_pos = $signed({bi_int, 16'd0}) + mul_13 + sum_p1;
    wire signed [37:0] tree_stage1_neg = $signed({x_old, 2'd0}) + mul_6;
    
    wire signed [37:0] total_sum = tree_stage1_pos - tree_stage1_neg;

    assign x_new = total_sum >>> 4;

endmodule