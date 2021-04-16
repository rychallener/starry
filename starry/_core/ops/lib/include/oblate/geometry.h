/**
\file geometry.h
\brief Circle-ellipse intersection stuff.

*/

#ifndef _STARRY_OBLATE_GEOMETRY_H_
#define _STARRY_OBLATE_GEOMETRY_H_

#include "../utils.h"
#include <Eigen/Eigenvalues>

namespace starry {
namespace oblate {
namespace geometry {

using namespace utils;

/**
    Polynomial root finder using an eigensolver.
    `coeffs` is a vector of coefficients, highest power first.

    Adapted from http://www.sgh1.net/posts/cpp-root-finder.md
*/
template <class Scalar>
inline std::vector<std::complex<Scalar>>
eigen_roots(const std::vector<Scalar> &coeffs, bool &success) {

  int matsz = coeffs.size() - 1;
  std::vector<std::complex<Scalar>> vret;
  Matrix<Scalar> companion_mat(matsz, matsz);
  companion_mat.setZero();

  for (int n = 0; n < matsz; ++n) {
    for (int m = 0; m < matsz; ++m) {

      if (n == m + 1)
        companion_mat(n, m) = 1.0;

      if (m == matsz - 1)
        companion_mat(n, m) = -coeffs[matsz - n] / coeffs[0];
    }
  }

  Eigen::EigenSolver<Matrix<Scalar>> solver(companion_mat);
  if (solver.info() == Eigen::Success) {
    success = true;
  } else {
    success = false;
  }

  Matrix<std::complex<Scalar>> eig = solver.eigenvalues();
  for (int i = 0; i < matsz; ++i)
    vret.push_back(eig(i));

  return vret;
}

/**
    Compute the points of intersection between a circle and an ellipse
    in the frame where the ellipse is centered at the origin,
    the semi-major axis of the ellipse is aligned with the x axis,
    and the circle is centered at `(xo, yo)`.

*/
template <class Scalar, int N>
inline Vector<ADScalar<Scalar, N>>
get_roots(const ADScalar<Scalar, N> &b_, const ADScalar<Scalar, N> &theta_,
          const ADScalar<Scalar, N> &costheta_,
          const ADScalar<Scalar, N> &sintheta_, const ADScalar<Scalar, N> &bo_,
          const ADScalar<Scalar, N> &ro_) {

  // Get the *values*
  using A = ADScalar<Scalar, N>;
  using Complex = std::complex<Scalar>;
  Scalar b = b_.value();
  Scalar costheta = costheta_.value();
  Scalar sintheta = sintheta_.value();
  Scalar bo = bo_.value();
  Scalar ro = ro_.value();

  // The result
  int nroots = 0;
  Vector<Scalar> x(4);

  // We'll solve for circle-ellipse intersections
  // in the frame where the ellipse is centered at the origin,
  // the semi-major axis of the ellipse is aligned with the x axis,
  // and the circle is centered at `(xo, yo)`.
  Scalar xo = bo * sintheta;
  Scalar yo = bo * costheta;

  // Useful quantities
  Scalar b2 = b * b;
  Scalar b4 = b2 * b2;
  Scalar ro2 = ro * ro;
  Scalar xo2 = xo * xo;
  Scalar yo2 = yo * yo;

  // Get the roots (eigenvalue problem)
  std::vector<Scalar> coeffs;
  coeffs.push_back((1 - b2) * (1 - b2));
  coeffs.push_back(-4 * xo * (1 - b2));
  coeffs.push_back(-2 *
                   (b4 + ro2 - 3 * xo2 - yo2 - b2 * (1 + ro2 - xo2 + yo2)));
  coeffs.push_back(-4 * xo * (b2 - ro2 + xo2 + yo2));
  coeffs.push_back(b4 - 2 * b2 * (ro2 - xo2 + yo2) +
                   (ro2 - xo2 - yo2) * (ro2 - xo2 - yo2));
  bool success = false;
  std::vector<std::complex<Scalar>> roots = eigen_roots(coeffs, success);
  if (!success) {
    std::stringstream args;
    args << "b_ = " << b_ << ", "
         << "theta_ = " << theta_ << ", "
         << "costheta_ = " << costheta_ << ", "
         << "sintheta_ = " << sintheta_ << ", "
         << "bo_ = " << bo_ << ", "
         << "ro_ = " << ro_;
    throw StarryException("Root eigensolver did not converge.",
                          "oblate/geometry.h", "get_roots", args.str());
  }

  // Polish the roots using Newton's method on the *original*
  // function, which is more stable than the quartic expression.
  Complex fA, fB, f, df, minx;
  Scalar absf, root;
  Eigen::Matrix<Scalar, 2, 2> diff;
  typename Eigen::Matrix<Scalar, 2, 2>::Index minRow, minCol;
  Vector<Scalar> error(4), s0(4), s1(4);
  Scalar p, q, v, w, t;
  for (int n = 0; n < 4; ++n) {
    /*
    We're looking for the intersection of the function

         y1 = +/- b * sqrt(1 - x^2)

    and the function

         y2 = yo +/- sqrt(ro^2 - (x - xo^2))

    Let's figure out which of the four cases (+/-, +/-) this
    root is a solution to. We're then going to polish
    the root by minimizing the function

         f = y1 - y2
    */
    fA = sqrt(1.0 - roots[n] * roots[n]);
    fB = sqrt(ro2 - (roots[n] - xo) * (roots[n] - xo));
    diff <<                       //
        abs(b * fA - (yo + fB)),  //
        abs(b * fA - (yo - fB)),  //
        abs(-b * fA - (yo + fB)), //
        abs(-b * fA - (yo - fB));
    absf = diff.minCoeff(&minRow, &minCol);
    s0(n) = minRow == 0 ? 1 : -1;
    s1(n) = minCol == 0 ? 1 : -1;

    // Apply Newton's method to polish the root
    error(n) = INFINITY;
    for (int k = 0; k < STARRY_ROOT_MAX_ITER; ++k) {
      fA = sqrt(1.0 - roots[n] * roots[n]);
      fB = sqrt(ro2 - (roots[n] - xo) * (roots[n] - xo));
      f = s0(n) * b * fA - (yo + s1(n) * fB);
      absf = abs(f);
      if (absf < error(n)) {
        error(n) = absf;
        minx = roots[n];
        if (error(n) <= STARRY_ROOT_TOL_HIGH)
          break;
      }
      df = -s0(n) * b * roots[n] / fA + s1(n) * (roots[n] - xo) / fB;
      roots[n] -= f / df;
    }
  }

  // Prune the roots until we have an even number.
  // Duplicate roots OK at this stage.
  Vector<int> good_roots(4);
  good_roots.setZero();
  Scalar tolmed = STARRY_ROOT_TOL_MED;
  Scalar tolhigh = STARRY_ROOT_TOL_HIGH;
  while (tolmed < STARRY_ROOT_TOL_LOW) {

    // Discard imaginary and unconverged roots
    for (int n = 0; n < 4; ++n) {

      // Only keep the root if the solver actually converged
      if (error(n) < tolmed) {

        // Only keep the root if it's real
        if ((abs(roots[n].imag()) < tolhigh) &&
            (abs(roots[n].real()) <= 1 + tolhigh)) {

          // Store the root
          good_roots(n) = 1;
        }
      }
    }

    if (is_even(good_roots.sum())) {

      // We're good!
      break;

    } else {

      // Repeat with relaxed constraints
      tolmed *= 10;
      tolhigh *= 10;
    }
  }

  // TODO: Duplicate roots should be allowed when
  // theta is +/- pi / 2 !!!

  // Finally, discard any duplicate roots
  // We'll discard *both*, since this corresponds
  // to a grazing configuration which we can just
  // ignore!
  for (int n = 0; n < 4; ++n) {
    for (int m = 0; m < n; ++m) {
      if (abs(roots[n] - roots[m]) < STARRY_ROOT_TOL_DUP) {
        if (good_roots(n) && good_roots(m)) {
          good_roots(n) = 0;
          good_roots(m) = 0;
        }
      }
    }
  }

  // Assemble the output vector
  nroots = good_roots.sum();
  Vector<A> result(nroots);
  int m = 0;
  for (int n = 0; n < 4; ++n) {
    if (good_roots(n)) {

      // Get the root
      root = roots[n].real();
      result(m).value() = root;

      // Compute the derivatives
      if (N > 0) {
        Scalar dxdb, dxdtheta, dxdbo, dxdro;
        q = sqrt(ro2 - (root - xo) * (root - xo));
        p = sqrt(1 - root * root);
        v = (root - xo) / q;
        w = b / p;
        t = 1.0 / (w * root - (s1(n) * s0(m)) * v);
        dxdb = t * p;
        dxdtheta = (s1(n) * sintheta * v - costheta) * (bo * t * s0(m));
        dxdbo = -(sintheta + s1(n) * costheta * v) * (t * s0(m));
        dxdro = -ro * t / q * s1(n) * s0(m);
        result(m).derivatives() =
            dxdb * b_.derivatives() + dxdtheta * theta_.derivatives() +
            dxdbo * bo_.derivatives() + dxdro * ro_.derivatives();
      }
      ++m;
    }
  }

  return result;
}

/**
    Compute the angles at which the circle intersects the ellipse
    in the frame where the ellipse is centered at the origin,
    the semi-major axis of the ellipse is at an angle `theta` with
    respect to the x axis, and the circle is centered at `(0, bo)`.

*/
template <class Scalar, int N>
inline void
get_angles(const ADScalar<Scalar, N> &bo_, const ADScalar<Scalar, N> &ro_,
           const ADScalar<Scalar, N> &f_, const ADScalar<Scalar, N> &theta_,
           ADScalar<Scalar, N> &phi1, ADScalar<Scalar, N> &phi2,
           ADScalar<Scalar, N> &xi1, ADScalar<Scalar, N> &xi2) {

  using A = ADScalar<Scalar, N>;

  // We may need to adjust these, so make a copy
  A bo = bo_;
  A ro = ro_;
  A f = f_;
  A b = 1 - f_;
  A theta = theta_;

  // Enforce bo >= 0
  if (bo < 0) {
    bo = -bo;
    theta -= pi<Scalar>();
  }

  // Avoid f = 0 issues
  if (f < STARRY_MIN_F) {
    f = STARRY_MIN_F;
    b = 1 - f;
  }

  A costheta = cos(theta);
  A sintheta = sin(theta);

  // Trivial cases
  if (bo <= ro - 1 + STARRY_COMPLETE_OCC_TOL) {

    // Complete occultation
    phi1 = phi2 = xi1 = xi2 = 0.0;
    return;

  } else if (bo + ro + f <= 1 + STARRY_GRAZING_TOL) {

    // Regular occultation, but occultor doesn't touch the limb
    phi2 = xi1 = 0.0;
    phi1 = xi2 = 2 * pi<Scalar>();
    return;

  } else if (bo >= 1 + ro - STARRY_NO_OCC_TOL) {

    // No occultation
    phi1 = phi2 = xi1 = 0.0;
    xi2 = 2 * pi<Scalar>();
    return;
  }

  // HACK: This grazing configuration leads to instabilities
  // in the root solver. Let's avoid it.
  if ((1 - ro - STARRY_GRAZING_TOL <= bo) &&
      (bo <= 1 - ro + STARRY_GRAZING_TOL))
    bo = 1 - ro + STARRY_GRAZING_TOL;

  // HACK: The eigensolver doesn't converge when ro = 1 and theta = pi / 2.
  if ((abs(1 - ro) < STARRY_THETA_UNIT_RADIUS_TOL) &&
      (abs(costheta) < STARRY_THETA_UNIT_RADIUS_TOL)) {
    costheta += (costheta > 0 ? STARRY_THETA_UNIT_RADIUS_TOL
                              : -STARRY_THETA_UNIT_RADIUS_TOL);
  }

  // Get the points of intersection between the circle & ellipse
  // These are the roots to a quartic equation.
  A xo = bo * sintheta;
  A yo = bo * costheta;
  Vector<A> x = get_roots(b, theta, costheta, sintheta, bo, ro);
  int nroots = x.size();

  if (nroots == 0) {

    // There are no intersections between the circle
    // and the ellipse. There are 3 possibilies.

    // Is the center of the circle outside the ellipse?
    if ((abs(xo) > 1) || (abs(yo) > b * sqrt(1 - xo * xo))) {

      // Is the center of the ellipse outside the circle?
      if (bo > ro) {

        // No occultation
        phi1 = phi2 = xi1 = 0.0;
        xi2 = 2 * pi<Scalar>();

      } else {

        // Complete occultation
        phi1 = phi2 = xi1 = xi2 = 0.0;
      }

    } else {

      // Regular occultation, but occultor doesn't touch the limb
      phi2 = xi1 = 0.0;
      phi1 = xi2 = 2 * pi<Scalar>();
    }

  } else if (nroots == 2) {

    // Regular occultation
    A y, rhs, xm, ym, mid;

    // First root
    y = b * sqrt(1 - x(0) * x(0));
    rhs = (ro * ro - (x(0) - xo) * (x(0) - xo));
    if (abs((y - yo) * (y - yo) - rhs) < abs((y + yo) * (y + yo) - rhs)) {
      phi1 = theta + atan2(y - yo, x(0) - xo);
      xi1 = atan2(sqrt(1 - x(0) * x(0)), x(0));
    } else {
      phi1 = theta - atan2(y + yo, x(0) - xo);
      xi1 = atan2(-sqrt(1 - x(0) * x(0)), x(0));
    }

    // Second root
    y = b * sqrt(1 - x(1) * x(1));
    rhs = (ro * ro - (x(1) - xo) * (x(1) - xo));
    if (abs((y - yo) * (y - yo) - rhs) < abs((y + yo) * (y + yo) - rhs)) {
      phi2 = theta + atan2(y - yo, x(1) - xo);
      xi2 = atan2(sqrt(1 - x(1) * x(1)), x(1));
    } else {
      phi2 = theta - atan2(y + yo, x(1) - xo);
      xi2 = atan2(-sqrt(1 - x(1) * x(1)), x(1));
    }

    // Wrap and sort the angles
    phi1 = angle(phi1);
    phi2 = angle(phi2);
    xi1 = angle(xi1);
    xi2 = angle(xi2);

    // xi is always counter-clockwise
    if (xi1 > xi2) {
      std::swap(xi1, xi2);
      std::swap(phi1, phi2);
    }

    // Ensure the T integral does not take us through the inside of the occultor
    mid = 0.5 * (xi1 + xi2);
    xm = cos(mid);
    ym = b * sin(mid);
    if ((xm - xo) * (xm - xo) + (ym - yo) * (ym - yo) < ro * ro) {
      std::swap(xi1, xi2);
      xi2 += 2 * pi<Scalar>();
    }

    // Ensure the P integral takes us through the inside of the star
    mid = 0.5 * (phi1 + phi2);
    xm = xo + ro * cos(theta - mid);
    ym = yo - ro * sin(theta - mid);
    if (ym * ym > b * b * (1 - xm * xm)) {
      if (phi1 < phi2) {
        phi1 += 2 * pi<Scalar>();
      } else {
        phi2 += 2 * pi<Scalar>();
      }
    }

    // phi is always clockwise
    if (phi2 > phi1) {
      std::swap(phi1, phi2);
    }

  } else {

    // Pathological case?
    std::stringstream args;
    args << "bo_ = " << bo_ << ", "
         << "ro_ = " << ro_ << ", "
         << "f_ = " << f_ << ", "
         << "theta_ = " << theta_;
    throw StarryException("Unexpected branch.", "oblate/geometry.h",
                          "get_angles", args.str());
  }
}

} // namespace geometry
} // namespace oblate
} // namespace starry

#endif
