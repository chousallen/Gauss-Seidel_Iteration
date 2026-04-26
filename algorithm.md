# Adaptation of Successive Over-Relaxation (SOR) Algorithm

The **Successive Over-Relaxation (SOR) method** is an iterative technique used to solve linear systems of the form **Ax = b**. It is derived by extrapolating the **Gauss-Seidel method** to accelerate the rate of convergence. Based on the specific $16 \times 16$ matrix $A$ and project requirements, the algorithm has been adapted as follows.

### 1. General SOR Formula
The general iterative formula for SOR calculates the $(k+1)$-th value of each element $x_i$ as a weighted average between its previous value and the new Gauss-Seidel iterate:

$$x_{i}^{(k+1)} = (1 - \omega)x_{i}^{(k)} + \frac{\omega}{a_{ii}} \left( b_{i} - \sum_{j < i} a_{ij}x_{j}^{(k+1)} - \sum_{j > i} a_{ij}x_{j}^{(k)} \right)$$

*   **$\omega$**: The **relaxation factor**. For convergence, $\omega$ must be in the interval $(0, 2)$.
*   **$a_{ii}$**: The diagonal elements of matrix $A$.
*   **Data Dependency**: Elements with indices $j < i$ use updated values from the current iteration ($x^{(k+1)}$), while indices $j > i$ use values from the previous iteration ($x^{(k)}$).

### 2. Adaptation to Matrix A
The provided **Matrix A** is a $16 \times 16$ banded matrix with specific constant coefficients:
*   **Diagonal elements ($a_{ii}$)**: All diagonal values are **20**.
*   **Off-diagonal elements**: The non-zero terms in each row are **-13**, **6**, and **-1**.

When these are substituted into the subtraction term $(b_i - \sum a_{ij}x_j)$ of the formula, the signs flip, resulting in the coefficients **+13**, **-6**, and **+1**.

### 3. Adapted Iterative Equations
The following equations represent the first iteration ($k=0$ to $k=1$) adapted for the 16 elements of vector $x$. Boundary conditions use **0** for any index $j$ that falls outside the range $$.

*   **For $x_1$**:
    $$x_{1}^{(1)} = (1 - \omega)x_{1}^{(0)} + \frac{\omega}{20} \left[ b_{1} + 13(x_{2}^{(0)} + 0) - 6(x_{3}^{(0)} + 0) + 1(x_{4}^{(0)} + 0) \right]$$
*   **For $x_2$**:
    $$x_{2}^{(1)} = (1 - \omega)x_{2}^{(0)} + \frac{\omega}{20} \left[ b_{2} + 13(x_{3}^{(0)} + x_{1}^{(1)}) - 6(x_{4}^{(0)} + 0) + 1(x_{5}^{(0)} + 0) \right]$$
*   **For $x_4$ (General Case)**:
    $$x_{4}^{(1)} = (1 - \omega)x_{4}^{(0)} + \frac{\omega}{20} \left[ b_{4} + 13(x_{5}^{(0)} + x_{3}^{(1)}) - 6(x_{6}^{(0)} + x_{2}^{(1)}) + 1(x_{7}^{(0)} + x_{1}^{(1)}) \right]$$
*   **For $x_{16}$**:
    $$x_{16}^{(1)} = (1 - \omega)x_{16}^{(0)} + \frac{\omega}{20} \left[ b_{16} + 13(0 + x_{15}^{(1)}) - 6(0 + x_{14}^{(1)}) + 1(0 + x_{13}^{(1)}) \right]$$

### 4. Implementation Constraints
To satisfy the requirements of the **Gauss-Seidel Iteration Machine (GSIM)**:
*   **Fixed-Point Arithmetic**: The input $b$ is a **16-bit 2's complement integer**, while the output $x$ must be a **32-bit 2's complement value** with 16 bits for the integer part and 16 bits for the decimal part.
*   **Hardware Efficiency**: The implementation should utilize optimizations such as **pipelining** (e.g., 3-stage) and **constant dividers** (dividing by 20) to improve the **AT score** (Area $\times$ Timing).
*   **Convergence**: The system is intended to converge after a set number of iterations ($M$), typically chosen by the designer (e.g., 30 iterations) to achieve an error rate of $E^2 < 0.000001$.