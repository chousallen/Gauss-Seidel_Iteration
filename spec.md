# Specification for Gauss-Seidel Iteration Machine (GSIM)

Based on **doc.pdf** and related sources, this document specifies the requirements for the GSIM circuit design, aimed at solving a system of linear equations ($Ax = b$).

## 1. Problem Description
The goal is to design an integrated circuit that solves a **linear system of equations** where **Matrix A** (16x16) and **Vector b** (16 elements) are known integer values. The machine takes inputs $b_1, b_2, \dots, b_{16}$ sequentially and outputs the calculated solutions $x_1, x_2, \dots, x_{16}$ after a series of iterations.

## 2. Hardware Interface
The GSIM system interacts with a Host using the following signals:

| Signal Name | I/O | Width | Description |
| :--- | :--- | :--- | :--- |
| **clk** | I | 1 | Synchronous system clock; data is sent on the rising edge. |
| **reset** | I | 1 | **Active high asynchronous** system reset. |
| **in_en** | I | 1 | Input enable; remains High while the 16 entries of $b$ are being sent. |
| **b_in** | I | 16 | Input bus for matrix B elements; **16-bit 2's complement integer**. |
| **x_out** | O | 32 | Output bus for solution vector X; **32-bit 2's complement** (16-bit integer, 16-bit decimal). |
| **out_valid**| O | 1 | High when the output data on `x_out` is valid. |

## 3. Mathematical Specifications

### Matrix A Definition
The system solves for a fixed **16x16 banded matrix A** defined in the sources. 
*   **Diagonal ($a_{ii}$)**: All diagonal elements are **20**.
*   **Off-diagonals**: Each row contains non-zero elements **-13**, **6**, and **-1** at specific offsets from the diagonal.

### Iteration Algorithm
The machine must implement the **Gauss-Seidel Iteration** method. A key characteristic is that updated values $x_j^{(k+1)}$ are used as soon as they are available within the same iteration for $j < i$.
*   **SOR Optimization**: As discussed in our conversation, the **Successive Over-Relaxation (SOR)** variant can be used with a relaxation factor **$\omega = 1.25$**.
*   **Simplified Division**: Choosing $\omega = 1.25$ allows the term $\frac{\omega}{20}$ to become **$1/16$**, which is implemented via a **4-bit right shift** instead of a complex divider [Previous Conversation].

## 4. Timing and Operation Flow
1.  **Initialization (T1)**: The system is reset for at least one clock cycle.
2.  **Data Input (T2-T3)**: The Host sends $b_1$ through $b_{16}$ over 16 consecutive cycles while `in_en` is High.
3.  **Calculation**: GSIM performs $M$ iterations (e.g., 30 iterations) to reach convergence.
4.  **Result Output (T4-T5)**: Once converged, the machine pulls `out_valid` High and outputs $x_1$ through $x_{16}$ sequentially.

## 5. Grading and Performance Criteria
To achieve high scores, the design must meet the following benchmarks:
*   **Accuracy (Rank A)**: The total error rate $E^2$ must be **less than 0.000001**.
*   **AT Score**: Performance is ranked by the product of **Synthesis Cell Area** and **Total Execution Time** (ns).
*   **Hardware Efficiency**: Designers are encouraged to use **pipelining** (e.g., 3-stage) and **parallel processing** to improve throughput and reduce area.
*   **Verification**: The design must pass five public testbenches and hidden patterns without timing violations or negative slack.