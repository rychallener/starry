import numpy as np
import os

np.seterr(invalid="ignore")

__all__ = ["generate_header"]


def get_f_exact(x, y, z, b):
    r"""
    Return the expression

    .. math::

        f \equiv
        \cos\theta_i 
        \mathrm{max}\left(0, \cos(\phi_r - \phi_i)\right)
        \sin\alpha \tan\beta

    from Equation (30) in Oren & Nayar (1994) as a function
    of the Cartesian coordinates on the sky-projected sphere
    seen at a phase where the semi-minor axis of the terminator
    is `b`.

    """
    bc = np.sqrt(1 - b ** 2)
    ci = bc * y - b * z
    f1 = -b / z - ci
    f2 = -b / ci - z
    f = ci * np.maximum(0, np.minimum(f1, f2))
    return f


def poly_basis(x, y, z, deg):
    """Return the polynomial basis evaluated at `x`, `y`, `z`."""
    N = (deg + 1) ** 2
    B = np.zeros((len(x * y * z), N))
    for n in range(N):
        l = int(np.floor(np.sqrt(n)))
        m = n - l * l - l
        mu = l - m
        nu = l + m
        if nu % 2 == 0:
            i = mu // 2
            j = nu // 2
            k = 0
        else:
            i = (mu - 1) // 2
            j = (nu - 1) // 2
            k = 1
        B[:, n] = x ** i * y ** j * z ** k
    return B


def get_w6(deg=4, Nb=3, res=100, inv_var=1e-4):
    """
    Return the coefficients of the 6D fit to `f`
    in `x`, `y`, `z`, `b`, and `bc`.

    """
    # Construct a 3D grid in (x, y, b)
    bgrid = np.linspace(-1, 0, res)
    xygrid = np.linspace(-1, 1, res)
    x, y, b = np.meshgrid(xygrid, xygrid, bgrid)
    z = np.sqrt(1 - x ** 2 - y ** 2)
    idx = np.isfinite(z) & (y > b * np.sqrt(1 - x ** 2))
    x = x[idx]
    y = y[idx]
    z = z[idx]
    b = b[idx]

    # Compute the exact `f` function on this grid
    f = get_f_exact(x, y, z, b)

    # Construct the design matrix for fitting
    # NOTE: The lowest power of `b` is *ONE*, since
    # we need `f = 0` eveywhere when `b = 0` for
    # a smooth transition to Lambertian at crescent
    # phase.
    N = (deg + 1) ** 2
    u = 0
    X = np.zeros((len(y * z * b), N * Nb ** 2))
    bc = np.sqrt(1 - b ** 2)
    B = poly_basis(x, y, z, deg)
    for n in range(N):
        for p in range(1, Nb + 1):
            for q in range(Nb):
                X[:, u] = B[:, n] * b ** p * bc ** q
                u += 1

    # Solve the linear problem
    w6 = np.linalg.solve(
        X.T.dot(X) + inv_var * np.eye(N * Nb ** 2), X.T.dot(f)
    )
    return w6


def generate_header(deg=4, Nb=3, res=100, inv_var=1e-4, nperline=3):
    assert deg >= 1, "deg must be >= 1"
    assert Nb >= 1, "Nb must be >= 1"
    w6 = get_w6(deg=deg, Nb=Nb, res=res, inv_var=inv_var)
    N = len(w6) - (len(w6) % nperline)
    string = "static const double STARRY_OREN_NAYAR_COEFFS[] = {\n"
    lines = w6[:N].reshape(-1, nperline)
    last_line = w6[N:]
    for i, line in enumerate(lines):
        string += ", ".join(["{:22.15e}".format(value) for value in line])
        if (i < len(lines) - 1) or (len(last_line)):
            string += ","
        string += "\n"
    string += ", ".join(["{:22.15e}".format(value) for value in last_line])
    string += "};"
    with open(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "oren_nayar.h"
        ),
        "w",
    ) as f:
        print("#ifndef _STARRY_REFLECTED_OREN_NAYAR_H_", file=f)
        print("#define _STARRY_REFLECTED_OREN_NAYAR_H_", file=f)
        print("", file=f)
        print("#define STARRY_OREN_NAYAR_DEG {}".format(deg), file=f)
        print("#define STARRY_OREN_NAYAR_N {}".format((deg + 1) ** 2), file=f)
        print("#define STARRY_OREN_NAYAR_NB {}".format(Nb), file=f)
        print("", file=f)
        print(string, file=f)
        print("#endif", file=f)