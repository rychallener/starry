#include "starry.h"

/**
Factorial for integers

*/
double factorial(int n) {
    if (n < 0)
        return INFINITY;
    return
        gsl_sf_fact(n);
}

/**
Factorial for floats

*/
double factorial(double n) {
    if (roundf(n) == n)
        return factorial((int)n);
    else
        return gsl_sf_gamma(n + 1);
}

/**
Compute the inverse of a matrix.

TODO: Our matrix is sparse and *rational*, so LU decomposition is
      not the most efficient way to compute the inverse!
*/
void invert(int N, double** invmat, double **matrix, double tol) {
    int i, j, signum;
    gsl_permutation* p = gsl_permutation_calloc(N);
    gsl_matrix* gsl_mat = gsl_matrix_calloc(N, N);
    gsl_matrix* gsl_invmat = gsl_matrix_alloc(N, N);

    // Copy the inverse over
    for (i=0; i<N; i++) {
        for (j=0; j<N; j++) {
            gsl_matrix_set(gsl_invmat, i, j, invmat[i][j]);
        }
    }

    // LU decomposition
    gsl_linalg_LU_decomp(gsl_invmat, p, &signum);
    gsl_linalg_LU_invert(gsl_invmat, p, gsl_mat);

    // Copy the matrix over
    for (i=0; i<N; i++) {
        for (j=0; j<N; j++) {
            if (abs(gsl_matrix_get(gsl_mat, i, j)) > tol)
                matrix[i][j] = gsl_matrix_get(gsl_mat, i, j);
            else
                matrix[i][j] = 0.;
        }
    }

    // Free
    gsl_matrix_free(gsl_invmat);
    gsl_matrix_free(gsl_mat);
    gsl_permutation_free(p);

    return;
}