# Adaptation of Successive Over-Relaxation (SOR) Algorithm

The **Successive Over-Relaxation (SOR) method** is an iterative technique used to solve linear systems of the form **Ax = b**. It is derived by extrapolating the **Gauss-Seidel method** to accelerate the rate of convergence. Based on the specific $16 \times 16$ matrix $A$ and project requirements, the algorithm has been adapted as follows.

### 1. Relaxation Factor Selection
To optimize the hardware implementation for the **Gauss-Seidel Iteration Machine (GSIM)**, we choose a **relaxation factor ($\omega$) of 1.25**. This value falls within the necessary interval of $(0, 2)$ to guarantee convergence for a positive definite system.

### 2. Simplification of the Iterative Term
The standard SOR formula includes the term $\frac{\omega}{a_{ii}}$ applied to the Gauss-Seidel iterate. In our system, the diagonal elements ($a_{ii}$) of **Matrix A** are all **20**. 

By selecting **$\omega = 1.25$**, the division term becomes significantly simpler for hardware logic:
$$\frac{\omega}{20} = \frac{1.25}{20} = \frac{5/4}{20} = \frac{5}{80} = \mathbf{\frac{1}{16}}$$

**Hardware Impact**:
*   **Simplified Division**: Dividing by 16 is implemented as a simple **4-bit right shift** in binary, entirely removing the need for a complex and area-intensive **constant divider** for the value 20.
*   **Weighting Term**: The term $(1 - \omega)x^{(0)}$ becomes **$-0.25x^{(0)}$**, which can be implemented as a **2-bit right shift** combined with a sign inversion.

### 3. Adapted Iterative Equations
The following equations represent the first iteration ($k=0$ to $k=1$) using the simplified factor of **1/16**. Boundary conditions use **0** for any index $j$ that falls outside the range $$.

*   **For $x_1$**:
    $$x_{1}^{(1)} = -0.25x_{1}^{(0)} + \frac{1}{16} \left[ b_{1} + 13(x_{2}^{(0)} + 0) - 6(x_{3}^{(0)} + 0) + 1(x_{4}^{(0)} + 0) \right]$$
*   **For $x_2$**:
    $$x_{2}^{(1)} = -0.25x_{2}^{(0)} + \frac{1}{16} \left[ b_{2} + 13(x_{3}^{(0)} + x_{1}^{(1)}) - 6(x_{4}^{(0)} + 0) + 1(x_{5}^{(0)} + 0) \right]$$
*   **For $x_4$ (General Case)**:
    $$x_{4}^{(1)} = -0.25x_{4}^{(0)} + \frac{1}{16} \left[ b_{4} + 13(x_{5}^{(0)} + x_{3}^{(1)}) - 6(x_{6}^{(0)} + x_{2}^{(1)}) + 1(x_{7}^{(0)} + x_{1}^{(1)}) \right]$$
*   **For $x_{16}$**:
    $$x_{16}^{(1)} = -0.25x_{16}^{(0)} + \frac{1}{16} \left[ b_{16} + 13(0 + x_{15}^{(1)}) - 6(0 + x_{14}^{(1)}) + 1(0 + x_{13}^{(1)}) \right]$$

### 4. Implementation Constraints
To satisfy the requirements of the **GSIM**:
*   **Fixed-Point Arithmetic**: The input $b$ is a **16-bit 2's complement integer**, while the output $x$ must be a **32-bit 2's complement value** (16-bit integer, 16-bit decimal).
*   **Hardware Efficiency**: Replacing the divider with shifts directly improves the **AT score** (Area $\times$ Timing) required for passing the synthesis benchmarks.
*   **Convergence**: Using SOR with $\omega=1.25$ will typically reach the required error rate of **$E^2 < 0.000001$** (Rank A) in fewer iterations than standard Gauss-Seidel.