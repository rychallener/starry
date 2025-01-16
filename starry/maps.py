# -*- coding: utf-8 -*-
from . import config, legacy
from ._constants import *
from ._core import (
    OpsYlm,
    OpsLD,
    OpsReflected,
    OpsRV,
    OpsOblate,
    OpsDoppler,
    math,
)
from ._core.utils import is_tensor
from ._indices import integers, get_ylm_inds, get_ul_inds, get_ylmw_inds
from ._plotting import (
    get_ortho_latitude_lines,
    get_ortho_longitude_lines,
    get_moll_latitude_lines,
    get_moll_longitude_lines,
    get_projection,
)
from .compat import evaluator
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import colors
from matplotlib.animation import FuncAnimation
from mpl_toolkits.axes_grid1 import make_axes_locatable
from IPython.display import HTML
from astropy import units
from scipy.ndimage import zoom
import os
import sys
import logging

logger = logging.getLogger("starry.maps")


__all__ = [
    "Map",
    "MapBase",
    "YlmBase",
    "LimbDarkenedBase",
    "RVBase",
    "ReflectedBase",
    "OblateBase",
    "DopplerBase",
]


class Amplitude(object):
    def __get__(self, instance, owner):
        return instance._amp

    def __set__(self, instance, value):
        instance._amp = instance._math.cast(np.ones(instance.nw) * value)


class MapBase(object):
    """The base class for all `starry` maps."""

    # The map amplitude
    amp = Amplitude()

    def _no_spectral(self):
        if self.nw is not None:  # pragma: no cover
            raise NotImplementedError(
                "Method not yet implemented for spectral maps."
            )

    def __init__(self, ydeg, udeg, fdeg, nw, **kwargs):
        # Instantiate the Theano ops class
        self.ops = self._ops_class_(ydeg, udeg, fdeg, nw, **kwargs)

        # Dimensions
        self._ydeg = ydeg
        self._Ny = (ydeg + 1) ** 2
        self._udeg = udeg
        self._Nu = udeg + 1
        self._fdeg = fdeg
        self._Nf = (fdeg + 1) ** 2
        self._deg = ydeg + udeg + fdeg
        self._N = (ydeg + udeg + fdeg + 1) ** 2
        self._nw = nw

        # Units
        self.angle_unit = kwargs.get("angle_unit", units.degree)
        self.wav_unit = kwargs.get("wav_unit", units.nm)

        # Initialize
        self.reset(**kwargs)

    @property
    def angle_unit(self):
        """An ``astropy.units`` quantity defining the angle unit for this map."""
        return self._angle_unit

    @angle_unit.setter
    def angle_unit(self, value):
        assert value.physical_type == "angle"
        self._angle_unit = value
        self._angle_factor = value.in_units(units.radian)

    @property
    def wav_unit(self):
        """An ``astropy.units`` quantity defining the wavelength unit for this map."""
        return self._wav_unit

    @angle_unit.setter
    def wav_unit(self, value):
        assert value.physical_type == "length"
        self._wav_unit = value
        self._wav_factor = value.in_units(units.m)

    @property
    def ydeg(self):
        """Spherical harmonic degree of the map. *Read-only*"""
        return self._ydeg

    @property
    def Ny(self):
        r"""Number of spherical harmonic coefficients. *Read-only*

        This is equal to :math:`(y_\mathrm{deg} + 1)^2`.
        """
        return self._Ny

    @property
    def udeg(self):
        """Limb darkening degree. *Read-only*"""
        return self._udeg

    @property
    def Nu(self):
        r"""Number of limb darkening coefficients, including :math:`u_0`. *Read-only*

        This is equal to :math:`u_\mathrm{deg} + 1`.
        """
        return self._Nu

    @property
    def fdeg(self):
        """Degree of the multiplicative filter. *Read-only*"""
        return self._fdeg

    @property
    def Nf(self):
        r"""Number of spherical harmonic coefficients in the filter. *Read-only*

        This is equal to :math:`(f_\mathrm{deg} + 1)^2`.
        """
        return self._Nf

    @property
    def deg(self):
        r"""Total degree of the map. *Read-only*

        This is equal to :math:`y_\mathrm{deg} + u_\mathrm{deg} + f_\mathrm{deg}`.
        """
        return self._deg

    @property
    def N(self):
        r"""Total number of map coefficients. *Read-only*

        This is equal to :math:`N_\mathrm{y} + N_\mathrm{u} + N_\mathrm{f}`.
        """
        return self._N

    @property
    def nw(self):
        """Number of wavelength bins. *Read-only*"""
        return self._nw

    @property
    def y(self):
        """The spherical harmonic coefficient vector. *Read-only*

        To set this vector, index the map directly using two indices:
        ``map[l, m] = ...`` where ``l`` is the spherical harmonic degree and
        ``m`` is the spherical harmonic order. These may be integers or
        arrays of integers. Slice notation may also be used.
        """
        return self._y

    @property
    def u(self):
        """The vector of limb darkening coefficients. *Read-only*

        To set this vector, index the map directly using one index:
        ``map[n] = ...`` where ``n`` is the degree of the limb darkening
        coefficient. This may be an integer or an array of integers.
        Slice notation may also be used.
        """
        return self._u

    @property
    def wav(self):
        """
        The wavelength(s) at which the flux is measured in units of ``wav_unit``.

        """
        return self._wav / self._wav_factor

    @wav.setter
    def wav(self, value):
        value = self._math.cast(value) * self._wav_factor
        if self._nw is None:
            assert value.ndim == 0, "Wavelength must be a scalar."
            self._wav = value
        else:
            assert value.ndim == 1, "Wavelength must be a vector."
            self._wav = value * self._math.ones(self._nw)

    def __getitem__(self, idx):
        if isinstance(idx, integers) or isinstance(idx, slice):
            # User is accessing a limb darkening index
            inds = get_ul_inds(self.udeg, idx)
            return self._u[inds]
        elif isinstance(idx, tuple) and len(idx) == 2 and self.nw is None:
            # User is accessing a Ylm index
            inds = get_ylm_inds(self.ydeg, idx[0], idx[1])
            return self._y[inds]
        elif isinstance(idx, tuple) and len(idx) == 3 and self.nw:
            # User is accessing a Ylmw index
            inds = get_ylmw_inds(self.ydeg, self.nw, idx[0], idx[1], idx[2])
            return self._y[inds]
        else:
            raise ValueError("Invalid map index.")

    def __setitem__(self, idx, val):
        if not is_tensor(val):
            val = np.array(val)
        if isinstance(idx, integers) or isinstance(idx, slice):
            # User is accessing a limb darkening index
            inds = get_ul_inds(self.udeg, idx)
            if 0 in inds:
                raise ValueError("The u_0 coefficient cannot be set.")
            self._u = self.ops.set_vector(self._u, inds, val)
        elif isinstance(idx, tuple) and len(idx) == 2 and self.nw is None:
            # User is accessing a Ylm index
            inds = get_ylm_inds(self.ydeg, idx[0], idx[1])
            if 0 in inds:
                if np.array_equal(np.sort(inds), np.arange(self.Ny)):
                    # The user is setting *all* coefficients, so we allow
                    # them to "set" the Y_{0,0} coefficient...
                    self._y = self.ops.set_vector(self._y, inds, val)
                    # ... except we scale the amplitude of the map and
                    # force Y_{0,0} to be unity.
                    self.amp = self._y[0]
                    self._y /= self._y[0]
                else:
                    raise ValueError(
                        "The Y_{0,0} coefficient cannot be set. "
                        "Please change the map amplitude instead."
                    )
            else:
                self._y = self.ops.set_vector(self._y, inds, val)
        elif isinstance(idx, tuple) and len(idx) == 3 and self.nw:
            # User is accessing a Ylmw index
            inds = get_ylmw_inds(self.ydeg, self.nw, idx[0], idx[1], idx[2])
            if 0 in inds[0]:
                if np.array_equal(
                    np.sort(inds[0].reshape(-1)), np.arange(self.Ny)
                ):
                    # The user is setting *all* coefficients, so we allow
                    # them to "set" the Y_{0,0} coefficient...
                    self._y = self.ops.set_matrix(
                        self._y, inds[0], inds[1], val
                    )
                    # ... except we scale the amplitude of the map and
                    # force Y_{0,0} to be unity.
                    self.amp = self.ops.set_vector(
                        self.amp, inds[1], self._y[0, inds[1]]
                    )
                    self._y /= self._y[0]
                else:
                    raise ValueError(
                        "The Y_{0,0} coefficient cannot be set. "
                        "Please change the map amplitude instead."
                    )
            else:
                self._y = self.ops.set_matrix(self._y, inds[0], inds[1], val)
        else:
            raise ValueError("Invalid map index.")

    def _get_norm(self, image_arr, **kwargs):
        norm = kwargs.get("norm", None)
        if norm is None:
            vmin = np.nanmin(image_arr)
            vmax = np.nanmax(image_arr)
            if np.abs(vmin - vmax) < 1e-9:
                vmin -= 1e-9
                vmax += 1e-9
            norm = colors.Normalize(vmin=vmin, vmax=vmax)
        return norm

    def _get_projection(self, **kwargs):
        return get_projection(kwargs.get("projection", "ortho"))

    def _get_ortho_borders(self, **kwargs):
        xp = np.linspace(-1, 1, 10000)
        yp = np.sqrt(1 - xp ** 2)
        xm = xp
        ym = -yp
        return xp, yp, xm, ym

    def _updatefig(
        self,
        i,
        img,
        image,
        img_overlay,
        overlay,
        projection,
        grid,
        lonlines,
        latlines,
        borders,
        kwargs,
    ):
        img.set_array(image[i])
        images = [img]
        if overlay is not None:
            img_overlay.set_array(overlay[i])
            images += [img_overlay]
        if (
            projection == STARRY_ORTHOGRAPHIC_PROJECTION
            and grid
            and len(image) > 1
            and self.nw is None
        ):
            lons = self._get_ortho_longitude_lines(i=i, **kwargs)
            for n, l in enumerate(lons):
                lonlines[n].set_xdata(l[0])
                lonlines[n].set_ydata(l[1])
        return tuple(images + lonlines + latlines + borders)

    def reset(self, **kwargs):
        """Reset all map coefficients and attributes.

        .. note::
            Does not reset custom unit settings.

        """
        if self.nw is None:
            y = np.zeros(self.Ny)
            y[0] = 1.0
            wav = kwargs.get("wav", 650.0)
        else:
            y = np.zeros((self.Ny, self.nw))
            y[0, :] = 1.0
            if self.nw == 1:
                wav = kwargs.get("wav", np.array([650.0]))
            else:
                wav = kwargs.get("wav", np.linspace(400.0, 900.0, self.nw))
        self._y = self._math.cast(y)
        self.wav = wav

        u = np.zeros(self.Nu)
        u[0] = -1.0
        self._u = self._math.cast(u)

        f = np.zeros(self.Nf)
        f[0] = np.pi
        self._f = self._math.cast(f)

        self._amp = self._math.cast(kwargs.get("amp", np.ones(self.nw)))

        # Reset data and priors
        self._flux = None
        self._C = None
        self._mu = None
        self._L = None
        self._solution = None

    def show(self, **kwargs):
        """
        Display an image of the map, with optional animation. See the
        docstring of :py:meth:`render` for more details and additional
        keywords accepted by this method.

        Args:
            ax (optional): A matplotlib axis instance to use. Default is
                to create a new figure.
            cmap (string or colormap instance, optional): The matplotlib colormap
                to use. Defaults to ``plasma``.
            figsize (tuple, optional): Figure size in inches. Default is
                (3, 3) for orthographic maps and (7, 3.5) for rectangular
                maps.
            projection (string, optional): The map projection. Accepted
                values are ``ortho``, corresponding to an orthographic
                projection (as seen on the sky), ``rect``, corresponding
                to an equirectangular latitude-longitude projection,
                and ``moll``, corresponding to a Mollweide equal-area
                projection. Defaults to ``ortho``.
            colorbar (bool, optional): Display a colorbar? Default is False.
            grid (bool, optional): Show latitude/longitude grid lines?
                Defaults to True.
            interval (int, optional): Interval between frames in milliseconds
                (animated maps only). Defaults to 75.
            file (string, optional): The file name (including the extension)
                to save the figure or animation to. Defaults to None.
            html5_video (bool, optional): If rendering in a Jupyter notebook,
                display as an HTML5 video? Default is True. If False, displays
                the animation using Javascript (file size will be larger.)
            dpi (int, optional): Image resolution in dots per square inch.
                Defaults to the value defined in ``matplotlib.rcParams``.
            bitrate (int, optional): Bitrate in kbps (animations only).
                Defaults to the value defined in ``matplotlib.rcParams``.
            norm (optional): The color normalization passed to
                ``matplotlib.pyplot.imshow``, an instance of
                ``matplotlib.colors.Normalize``. Can be used to pass in
                minimum and maximum values. Default is None.
            illuminate (bool, optional): Illuminate the map (reflected light
                maps only)? Default True. If False, shows the albedo
                surface map.
            screen (bool, optional): Apply the illumination as a
                black-and-white alpha screen (reflected light maps only)?
                Default True. If False, a single colormap is used to
                plot the visible intensity.

        .. note::
            Pure limb-darkened maps do not accept a ``projection`` keyword.

        .. note::
            If calling this method on an instance of ``Map`` created within
            a ``pymc3.Model()``, you may specify a ``point`` keyword with
            the model point at which to evaluate the map. This method also
            accepts a ``model`` keyword, although this is inferred
            automatically if called from within a ``pymc3.Model()`` context.
            If no point is provided, attempts to evaluate the map at
            ``model.test_point`` and raises a warning.

        """
        # Get kwargs
        get_val = evaluator(**kwargs)
        cmap = kwargs.pop("cmap", "plasma")
        grid = kwargs.pop("grid", True)
        interval = kwargs.pop("interval", 75)
        file = kwargs.pop("file", None)
        html5_video = kwargs.pop("html5_video", True)
        dpi = kwargs.pop("dpi", None)
        figsize = kwargs.pop("figsize", None)
        bitrate = kwargs.pop("bitrate", None)
        colorbar = kwargs.pop("colorbar", False)
        colorbar_size = kwargs.pop("colorbar_size", "5%")
        colorbar_pad = kwargs.pop("colorbar_pad", 0.05)
        ax = kwargs.pop("ax", None)
        if ax is None:
            custom_ax = False
        else:
            custom_ax = True

        # Render the map if needed
        image = kwargs.get("image", None)  # undocumented, used internally
        overlay = kwargs.get("overlay", None)  # undocumented, used internally
        if image is None:
            image = self._render_greedy(**kwargs)
        if len(image.shape) == 3:
            nframes = image.shape[0]
        else:
            nframes = 1
            image = np.reshape(image, (1,) + image.shape)
            if overlay is not None:
                overlay = np.reshape(overlay, (1,) + overlay.shape)

        # Additional kwargs
        projection = self._get_projection(**kwargs)
        norm = self._get_norm(image, **kwargs)

        # Animation
        animated = nframes > 1
        borders = []
        latlines = []
        lonlines = []

        # Set up the figure
        if projection != STARRY_ORTHOGRAPHIC_PROJECTION:

            # Set up the plot
            if figsize is None:
                figsize = (7, 3.75)
            if ax is None:
                fig, ax = plt.subplots(1, figsize=figsize)
            else:
                fig = ax.figure

            if projection == STARRY_RECTANGULAR_PROJECTION:

                # Equirectangular
                extent = (-180, 180, -90, 90)
                if grid:
                    lats = np.linspace(-90, 90, 7)[1:-1]
                    lons = np.linspace(-180, 180, 13)
                    latlines = [None for n in lats]
                    for n, lat in enumerate(lats):
                        latlines[n] = ax.axhline(
                            lat, color="k", lw=0.5, alpha=0.5, zorder=0
                        )
                    lonlines = [None for n in lons]
                    for n, lon in enumerate(lons):
                        lonlines[n] = ax.axvline(
                            lon, color="k", lw=0.5, alpha=0.5, zorder=0
                        )
                    ax.set_xticks(lons)
                    ax.set_yticks(lats)
                    for tick in (
                        ax.xaxis.get_major_ticks() + ax.yaxis.get_major_ticks()
                    ):
                        tick.label1.set_fontsize(10)
                    ax.set_xlabel("Longitude [deg]")
                    ax.set_ylabel("Latitude [deg]")

            else:

                # Mollweide
                dx = 2.0 / image.shape[1]
                extent = (
                    -(1 + dx) * 2 * np.sqrt(2),
                    2 * np.sqrt(2),
                    -(1 + dx) * np.sqrt(2),
                    np.sqrt(2),
                )
                ax.axis("off")
                ax.set_xlim(-2 * np.sqrt(2) - 0.05, 2 * np.sqrt(2) + 0.05)
                ax.set_ylim(-np.sqrt(2) - 0.05, np.sqrt(2) + 0.05)

                # Anti-aliasing at the edges
                x = np.linspace(-2 * np.sqrt(2), 2 * np.sqrt(2), 10000)
                y = np.sqrt(2) * np.sqrt(1 - (x / (2 * np.sqrt(2))) ** 2)
                borders += [
                    ax.fill_between(x, 1.1 * y, y, color="w", zorder=-1)
                ]
                borders += [
                    ax.fill_betweenx(
                        0.5 * x, 2.2 * y, 2 * y, color="w", zorder=-1
                    )
                ]
                borders += [
                    ax.fill_between(x, -1.1 * y, -y, color="w", zorder=-1)
                ]
                borders += [
                    ax.fill_betweenx(
                        0.5 * x, -2.2 * y, -2 * y, color="w", zorder=-1
                    )
                ]

                if grid:
                    x = np.linspace(-2 * np.sqrt(2), 2 * np.sqrt(2), 10000)
                    a = np.sqrt(2)
                    b = 2 * np.sqrt(2)
                    y = a * np.sqrt(1 - (x / b) ** 2)
                    borders += ax.plot(x, y, "k-", alpha=1, lw=1.5, zorder=0)
                    borders += ax.plot(x, -y, "k-", alpha=1, lw=1.5, zorder=0)
                    lats = get_moll_latitude_lines()
                    latlines = [None for n in lats]
                    for n, l in enumerate(lats):
                        (latlines[n],) = ax.plot(
                            l[0], l[1], "k-", lw=0.5, alpha=0.5, zorder=0
                        )
                    lons = get_moll_longitude_lines()
                    lonlines = [None for n in lons]
                    for n, l in enumerate(lons):
                        (lonlines[n],) = ax.plot(
                            l[0], l[1], "k-", lw=0.5, alpha=0.5, zorder=0
                        )

        else:

            # Orthographic
            if figsize is None:
                figsize = (3, 3)
            if ax is None:
                fig, ax = plt.subplots(1, figsize=figsize)
            else:
                fig = ax.figure
            ax.axis("off")
            ax.set_xlim(-1.05, 1.05)
            ax.set_ylim(-1.05, 1.05)
            dx = 2.0 / image.shape[1]
            extent = (-1 - dx, 1, -1 - dx, 1)

            # Anti-aliasing at the edges
            xp, yp, xm, ym = self._get_ortho_borders()
            borders += [
                ax.fill_between(xp, 1.1 * yp, yp, color="w", zorder=-1)
            ]
            borders += [
                ax.fill_between(xm, 1.1 * ym, ym, color="w", zorder=-1)
            ]

            # Grid lines
            if grid:
                borders += ax.plot(xp, yp, "k-", alpha=1, lw=1.5, zorder=0)
                borders += ax.plot(xm, ym, "k-", alpha=1, lw=1.5, zorder=0)
                lats = self._get_ortho_latitude_lines(**kwargs)
                latlines = [None for n in lats]
                for n, l in enumerate(lats):
                    (latlines[n],) = ax.plot(
                        l[0], l[1], "k-", lw=0.5, alpha=0.5, zorder=0
                    )
                lons = self._get_ortho_longitude_lines(**kwargs)
                lonlines = [None for n in lons]
                for n, l in enumerate(lons):
                    (lonlines[n],) = ax.plot(
                        l[0], l[1], "k-", lw=0.5, alpha=0.5, zorder=0
                    )

        img = ax.imshow(
            image[0],
            origin="lower",
            extent=extent,
            cmap=cmap,
            norm=norm,
            interpolation="none",
            animated=animated,
            zorder=-3,
        )

        if overlay is None:
            img_overlay = None
        else:
            cmapI = colors.LinearSegmentedColormap.from_list(
                "overlay", ["k", "k"], 256
            )
            cmapI._init()
            alphas = np.linspace(1.0, 0.0, cmapI.N + 3)
            cmapI._lut[:, -1] = alphas
            cmapI.set_under((0, 0, 0, 1))
            cmapI.set_over((0, 0, 0, 0))
            img_overlay = ax.imshow(
                overlay[0],
                origin="lower",
                extent=extent,
                cmap=cmapI,
                vmin=0,
                vmax=1,
                interpolation="none",
                animated=animated,
                zorder=-2,
            )

        # Add a colorbar
        if colorbar:
            if not custom_ax:
                fig.subplots_adjust(right=0.85)
            divider = make_axes_locatable(ax)
            cax = divider.append_axes(
                position="right", size=colorbar_size, pad=colorbar_pad
            )
            fig.colorbar(img, cax=cax, orientation="vertical")

        # Display or save the image / animation
        if animated:

            ani = FuncAnimation(
                fig,
                self._updatefig,
                fargs=(
                    img,
                    image,
                    img_overlay,
                    overlay,
                    projection,
                    grid,
                    lonlines,
                    latlines,
                    borders,
                    kwargs,
                ),
                interval=interval,
                blit=True,
                frames=image.shape[0],
            )

            # Business as usual
            if (file is not None) and (file != ""):
                if file.endswith(".mp4"):
                    ani.save(file, writer="ffmpeg", dpi=dpi, bitrate=bitrate)
                elif file.endswith(".gif"):
                    ani.save(
                        file, writer="imagemagick", dpi=dpi, bitrate=bitrate
                    )
                else:
                    # Try and see what happens!
                    ani.save(file, dpi=dpi, bitrate=bitrate)
                if not custom_ax:
                    plt.close()
            else:  # pragma: no cover
                try:
                    if "zmqshell" in str(type(get_ipython())):
                        plt.close()
                        with matplotlib.rc_context(
                            {
                                "savefig.dpi": dpi
                                if dpi is not None
                                else "figure",
                                "animation.bitrate": bitrate
                                if bitrate is not None
                                else -1,
                            }
                        ):
                            if html5_video:
                                display(HTML(ani.to_html5_video()))
                            else:
                                display(HTML(ani.to_jshtml()))
                    else:
                        raise NameError("")
                except NameError:
                    plt.show()
                    plt.close()

            # Matplotlib generates an annoying empty
            # file when producing an animation. Delete it.
            try:
                os.remove("None0000000.png")
            except FileNotFoundError:
                pass

        else:
            if (file is not None) and (file != ""):
                if (
                    not self.__props__["limbdarkened"]
                    and projection == STARRY_ORTHOGRAPHIC_PROJECTION
                ):
                    fig.subplots_adjust(
                        left=0.01, right=0.99, bottom=0.01, top=0.99
                    )
                fig.savefig(file, bbox_inches="tight")
                if not custom_ax:
                    plt.close()
            elif not custom_ax:
                plt.show()

    def limbdark_is_physical(self):
        """Check whether the limb darkening profile (if any) is physical.

        This method uses Sturm's theorem to ensure that the limb darkening
        intensity is positive everywhere and decreases monotonically toward
        the limb.

        Returns:
            bool: Whether or not the limb darkening profile is physical.
        """
        result = self.ops.limbdark_is_physical(self.u)
        if self.lazy:
            return result
        else:
            return bool(result)

    def set_data(self, flux, C=None, cho_C=None):
        """Set the data vector and covariance matrix.

        This method is required by the :py:meth:`solve` method, which
        analytically computes the posterior over surface maps given a
        dataset and a prior, provided both are described as multivariate
        Gaussians.

        Args:
            flux (vector): The observed light curve.
            C (scalar, vector, or matrix): The data covariance. This may be
                a scalar, in which case the noise is assumed to be
                homoscedastic, a vector, in which case the covariance
                is assumed to be diagonal, or a matrix specifying the full
                covariance of the dataset. Default is None. Either `C` or
                `cho_C` must be provided.
            cho_C (matrix): The lower Cholesky factorization of the data
                covariance matrix. Defaults to None. Either `C` or
                `cho_C` must be provided.
        """
        self._flux = self._math.cast(flux)
        self._C = self._linalg.Covariance(C, cho_C, N=self._flux.shape[0])

    def set_prior(self, *, mu=None, L=None, cho_L=None):
        """Set the prior mean and covariance of the spherical harmonic coefficients.

        This method is required by the :py:meth:`solve` method, which
        analytically computes the posterior over surface maps given a
        dataset and a prior, provided both are described as multivariate
        Gaussians.

        Note that the prior is placed on the **amplitude-weighted** coefficients,
        i.e., the quantity ``x = map.amp * map.y``. Because the first spherical
        harmonic coefficient is fixed at unity, ``x[0]`` is
        the amplitude of the map. The actual spherical harmonic coefficients
        are given by ``x / map.amp``.

        This convention allows one to linearly fit for an arbitrary map normalization
        at the same time as the spherical harmonic coefficients, while ensuring
        the ``starry`` requirement that the coefficient of the :math:`Y_{0,0}`
        harmonic is always unity.

        Args:
            mu (scalar or vector): The prior mean on the amplitude-weighted
                spherical harmonic coefficients. Default is `1.0` for the
                first term and zero for the remaining terms. If this is a vector,
                it must have length equal to :py:attr:`Ny`.
            L (scalar, vector, or matrix): The prior covariance. This may be
                a scalar, in which case the covariance is assumed to be
                homoscedastic, a vector, in which case the covariance
                is assumed to be diagonal, or a matrix specifying the full
                prior covariance. Default is None. Either `L` or
                `cho_L` must be provided.
            cho_L (matrix): The lower Cholesky factorization of the prior
                covariance matrix. Defaults to None. Either `L` or
                `cho_L` must be provided.

        """
        if mu is None:
            mu = np.zeros(self.Ny)
            mu[0] = 1.0
            mu = self._math.cast(mu)
        self._mu = self._math.cast(mu) * self._math.cast(np.ones(self.Ny))
        self._L = self._linalg.Covariance(L, cho_L, N=self.Ny)

    def remove_prior(self):
        """Remove the prior on the map coefficients."""
        self._mu = None
        self._L = None

    def solve(self, *, design_matrix=None, **kwargs):
        """Solve the linear least-squares problem for the posterior over maps.

        This method solves the generalized least squares problem given a
        light curve and its covariance (set via the :py:meth:`set_data` method)
        and a Gaussian prior on the spherical harmonic coefficients
        (set via the :py:meth:`set_prior` method). The map amplitude and
        coefficients are set to the maximum a posteriori (MAP) solution.

        Args:
            design_matrix (matrix, optional): The flux design matrix, the
                quantity returned by :py:meth:`design_matrix`. Default is
                None, in which case this is computed based on ``kwargs``.
            kwargs (optional): Keyword arguments to be passed directly to
                :py:meth:`design_matrix`, if a design matrix is not provided.

        Returns:
            A tuple containing the posterior mean for the amplitude-weighted \
            spherical harmonic coefficients (a vector) and the Cholesky factorization \
            of the posterior covariance (a lower triangular matrix).

        .. note::
            Users may call :py:meth:`draw` to draw from the
            posterior after calling this method.

        """
        # Not implemented for spectral
        self._no_spectral()

        if self._flux is None or self._C is None:
            raise ValueError("Please provide a dataset with `set_data()`.")
        elif self._mu is None or self._L is None:
            raise ValueError("Please provide a prior with `set_prior()`.")

        # Get the design matrix & remove any amplitude weighting
        if design_matrix is None:
            design_matrix = self.design_matrix(**kwargs)
        X = self._math.cast(design_matrix)

        # Compute the MAP solution
        self._solution = self._linalg.solve(
            X, self._flux, self._C.cholesky, self._mu, self._L.inverse
        )

        # Set the amplitude and coefficients
        x, _ = self._solution
        self.amp = x[0]
        if self.ydeg > 0:
            self[1:, :] = x[1:] / self.amp

        # Return the mean and covariance
        return self._solution

    def lnlike(self, *, design_matrix=None, woodbury=True, **kwargs):
        """Returns the log marginal likelihood of the data given a design matrix.

        This method computes the marginal likelihood (marginalized over the
        spherical harmonic coefficients) given a
        light curve and its covariance (set via the :py:meth:`set_data` method)
        and a Gaussian prior on the spherical harmonic coefficients
        (set via the :py:meth:`set_prior` method).

        Args:
            design_matrix (matrix, optional): The flux design matrix, the
                quantity returned by :py:meth:`design_matrix`. Default is
                None, in which case this is computed based on ``kwargs``.
            woodbury (bool, optional): Solve the linear problem using the
                Woodbury identity? Default is True. The
                `Woodbury identity <https://en.wikipedia.org/wiki/Woodbury_matrix_identity>`_
                is used to speed up matrix operations in the case that the
                number of data points is much larger than the number of
                spherical harmonic coefficients. In this limit, it can
                speed up the code by more than an order of magnitude. Keep
                in mind that the numerical stability of the Woodbury identity
                is not great, so if you're getting strange results try
                disabling this. It's also a good idea to disable this in the
                limit of few data points and large spherical harmonic degree.
            kwargs (optional): Keyword arguments to be passed directly to
                :py:meth:`design_matrix`, if a design matrix is not provided.

        Returns:
            The log marginal likelihood, a scalar.
        """
        # Not implemented for spectral
        self._no_spectral()

        if self._flux is None or self._C is None:
            raise ValueError("Please provide a dataset with `set_data()`.")
        elif self._mu is None or self._L is None:
            raise ValueError("Please provide a prior with `set_prior()`.")

        # Get the design matrix & remove any amplitude weighting
        if design_matrix is None:
            design_matrix = self.design_matrix(**kwargs)
        X = self._math.cast(design_matrix)

        # Compute the likelihood
        if woodbury:
            return self._linalg.lnlike_woodbury(
                X,
                self._flux,
                self._C.inverse,
                self._mu,
                self._L.inverse,
                self._C.lndet,
                self._L.lndet,
            )
        else:
            return self._linalg.lnlike(
                X, self._flux, self._C.value, self._mu, self._L.value
            )

    @property
    def solution(self):
        r"""The posterior probability distribution for the map.

        This is a tuple containing the mean and lower Cholesky factorization of the
        covariance of the amplitude-weighted spherical harmonic coefficient vector,
        obtained by solving the regularized least-squares problem
        via the :py:meth:`solve` method.

        Note that to obtain the actual covariance matrix from the lower Cholesky
        factorization :math:`L`, simply compute :math:`L L^\top`.

        Note also that this is the posterior for the **amplitude-weighted**
        map vector. Under this convention, the map amplitude is equal to the
        first term of the vector and the spherical harmonic coefficients are
        equal to the vector normalized by the first term.
        """
        if self._solution is None:
            raise ValueError("Please call `solve()` first.")
        return self._solution

    def draw(self):
        """Draw a map from the posterior distribution.

        This method draws a random map from the posterior distribution and
        sets the :py:attr:`y` map vector and :py:attr:`amp` map amplitude
        accordingly. Users should call :py:meth:`solve` to enable this
        attribute.
        """
        if self._solution is None:
            raise ValueError("Please call `solve()` first.")

        # Fast multivariate sampling using the Cholesky factorization
        yhat, cho_ycov = self._solution
        u = self._math.cast(np.random.randn(self.Ny))
        x = yhat + self._math.dot(cho_ycov, u)
        self.amp = x[0]
        self[1:, :] = x[1:] / self.amp


class YlmBase(legacy.YlmBase):
    """The default ``starry`` map class.

    This class handles light curves and phase curves of objects in
    emitted light.

    .. note::
        Instantiate this class by calling :py:func:`starry.Map` with
        ``ydeg > 0`` and both ``rv`` and ``reflected`` set to False.
    """

    _ops_class_ = OpsYlm

    def _render_greedy(self, **kwargs):
        get_val = evaluator(**kwargs)
        amp = get_val(self.amp).reshape(-1, 1, 1)
        return amp * self.ops.render(
            kwargs.get("res", 300),
            get_projection(kwargs.get("projection", "ortho")),
            np.atleast_1d(get_val(kwargs.get("theta", 0.0)))
            * self._angle_factor,
            get_val(self._inc),
            get_val(self._obl),
            get_val(self._y),
            get_val(self._u),
            get_val(self._f),
        )

    def _get_ortho_latitude_lines(self, **kwargs):
        get_val = evaluator(**kwargs)
        inc = get_val(self._inc)
        obl = get_val(self._obl)
        return get_ortho_latitude_lines(inc=inc, obl=obl)

    def _get_ortho_longitude_lines(self, i=0, **kwargs):
        get_val = evaluator(**kwargs)
        inc = get_val(self._inc)
        obl = get_val(self._obl)
        theta = (
            np.atleast_1d(get_val(kwargs.get("theta", 0.0)))
            * self._angle_factor
        )
        return get_ortho_longitude_lines(inc=inc, obl=obl, theta=theta[i])

    def _get_flux_kwargs(self, kwargs):
        xo = kwargs.get("xo", 0.0)
        yo = kwargs.get("yo", 0.0)
        zo = kwargs.get("zo", 1.0)
        ro = kwargs.get("ro", 0.0)
        theta = kwargs.get("theta", 0.0)
        theta, xo, yo, zo = self._math.vectorize(theta, xo, yo, zo)
        theta, xo, yo, zo, ro = self._math.cast(theta, xo, yo, zo, ro)
        theta *= self._angle_factor
        return theta, xo, yo, zo, ro

    def reset(self, **kwargs):
        if kwargs.get("inc", None) is not None:
            self.inc = kwargs.get("inc")
        else:
            self._inc = self._math.cast(0.5 * np.pi)

        if kwargs.get("obl", None) is not None:
            self.obl = kwargs.get("obl")
        else:
            self._obl = self._math.cast(0.0)

        super(YlmBase, self).reset(**kwargs)

    @property
    def inc(self):
        """The inclination of the rotation axis in units of :py:attr:`angle_unit`."""
        return self._inc / self._angle_factor

    @inc.setter
    def inc(self, value):
        self._inc = self._math.cast(value) * self._angle_factor

    @property
    def obl(self):
        """The obliquity of the rotation axis in units of :py:attr:`angle_unit`."""
        return self._obl / self._angle_factor

    @obl.setter
    def obl(self, value):
        self._obl = self._math.cast(value) * self._angle_factor

    def design_matrix(self, **kwargs):
        r"""Compute and return the light curve design matrix :math:`A`.

        This matrix is used to compute the flux :math:`f` from a vector of spherical
        harmonic coefficients :math:`y` and the map amplitude :math:`a`:
        :math:`f = a A y`.

        Args:
            xo (scalar or vector, optional): x coordinate of the occultor
                relative to this body in units of this body's radius.
            yo (scalar or vector, optional): y coordinate of the occultor
                relative to this body in units of this body's radius.
            zo (scalar or vector, optional): z coordinate of the occultor
                relative to this body in units of this body's radius.
            ro (scalar, optional): Radius of the occultor in units of
                this body's radius.
            theta (scalar or vector, optional): Angular phase of the body
                in units of :py:attr:`angle_unit`.
        """
        # Orbital kwargs
        theta, xo, yo, zo, ro = self._get_flux_kwargs(kwargs)

        # Compute & return
        return self.ops.X(
            theta, xo, yo, zo, ro, self._inc, self._obl, self._u, self._f
        )

    def intensity_design_matrix(self, lat=0, lon=0):
        """Compute and return the pixelization matrix ``P``.

        This matrix is used to compute the intensity :math:`I` from a vector of spherical
        harmonic coefficients :math:`y` and the map amplitude :math:`a`:
        :math:`I = a P y`.

        Args:
            lat (scalar or vector, optional): latitude at which to evaluate
                the design matrix in units of :py:attr:`angle_unit`.
            lon (scalar or vector, optional): longitude at which to evaluate
                the design matrix in units of :py:attr:`angle_unit`.

        .. note::
            This method ignores any filters (such as limb darkening
            or velocity weighting) and illumination (for reflected light
            maps).

        """
        # Get the Cartesian points
        lat, lon = self._math.vectorize(*self._math.cast(lat, lon))
        lat *= self._angle_factor
        lon *= self._angle_factor

        # Compute & return
        return self.ops.P(lat, lon)

    def flux(self, **kwargs):
        """
        Compute and return the light curve.

        Args:
            xo (scalar or vector, optional): x coordinate of the occultor
                relative to this body in units of this body's radius.
            yo (scalar or vector, optional): y coordinate of the occultor
                relative to this body in units of this body's radius.
            zo (scalar or vector, optional): z coordinate of the occultor
                relative to this body in units of this body's radius.
            ro (scalar, optional): Radius of the occultor in units of
                this body's radius.
            theta (scalar or vector, optional): Angular phase of the body
                in units of :py:attr:`angle_unit`.
            integrated (bool, optional): If True, dots the flux with the
                amplitude. Default False, in which case this returns a
                2d array (wavelength-dependent maps only).
        """
        # Orbital kwargs
        theta, xo, yo, zo, ro = self._get_flux_kwargs(kwargs)

        # Compute & return
        flux = self.ops.flux(
            theta,
            xo,
            yo,
            zo,
            ro,
            self._inc,
            self._obl,
            self._y,
            self._u,
            self._f,
        )

        if kwargs.get("integrated", False):
            return self._math.dot(flux, self.amp)
        else:
            return self.amp * flux

    def intensity(self, lat=0, lon=0, **kwargs):
        """
        Compute and return the intensity of the map.

        Args:
            lat (scalar or vector, optional): latitude at which to evaluate
                the intensity in units of :py:attr:`angle_unit`.
            lon (scalar or vector, optional): longitude at which to evaluate
                the intensity in units of :py:attr:`angle_unit``.
            theta (scalar, optional): For differentially rotating maps only,
                the angular phase at which to evaluate the intensity.
                Default 0.
            limbdarken (bool, optional): Apply limb darkening
                (only if :py:attr:`udeg` > 0)? Default True.

        """
        # Get the Cartesian points
        lat, lon = self._math.vectorize(*self._math.cast(lat, lon))
        lat *= self._angle_factor
        lon *= self._angle_factor

        # If differentially rotating, allow a `theta` keyword
        theta = self._math.cast(kwargs.get("theta", 0.0))
        theta *= self._angle_factor

        # If limb-darkened, allow a `limbdarken` keyword
        if kwargs.get("limbdarken", True) and self.udeg > 0:
            ld = np.array(True)
        else:
            ld = np.array(False)

        # Compute & return
        return self.amp * self.ops.intensity(
            lat, lon, self._y, self._u, self._f, theta, ld
        )

    def render(self, res=300, projection="ortho", theta=0.0):
        """Compute and return the intensity of the map on a grid.

        Returns an image of shape ``(res, res)``, unless ``theta`` is a vector,
        in which case returns an array of shape ``(nframes, res, res)``, where
        ``nframes`` is the number of values of ``theta``. However, if this is
        a spectral map, ``nframes`` is the number of wavelength bins and
        ``theta`` must be a scalar.

        .. note::

            Users can obtain the latitudes and longitudes corresponding to
            each point in the rendered image by calling
            :py:meth:`get_latlon_grid()`.

        Args:
            res (int, optional): The resolution of the map in pixels on a
                side. Defaults to 300.
            projection (string, optional): The map projection. Accepted
                values are ``ortho``, corresponding to an orthographic
                projection (as seen on the sky), ``rect``, corresponding
                to an equirectangular latitude-longitude projection,
                and ``moll``, corresponding to a Mollweide equal-area
                projection. Defaults to ``ortho``.
            theta (scalar or vector, optional): The map rotation phase in
                units of :py:attr:`angle_unit`. If this is a vector, an
                animation is generated. Defaults to ``0.0``.
        """
        # Multiple frames?
        if self.nw is not None:
            animated = True
        else:
            if is_tensor(theta):
                animated = hasattr(theta, "ndim") and theta.ndim > 0
            else:
                animated = hasattr(theta, "__len__")

        # Convert
        projection = get_projection(projection)
        theta = self._math.vectorize(
            self._math.cast(theta) * self._angle_factor
        )

        # Compute
        if self.nw is None or self.lazy:
            amp = self.amp
        else:
            # The intensity has shape `(nw, res, res)`
            # so we must reshape `amp` to take the product correctly
            amp = self.amp[:, np.newaxis, np.newaxis]
        image = amp * self.ops.render(
            res,
            projection,
            theta,
            self._inc,
            self._obl,
            self._y,
            self._u,
            self._f,
        )

        # Squeeze?
        if animated:
            return image
        else:
            return self._math.reshape(image, [res, res])

    def get_latlon_grid(self, res=300, projection="ortho"):
        """Return the latitude/longitude grid corresponding to the result
        of a call to :py:meth:`render()`.

        Args:
            res (int, optional): The resolution of the map in pixels on a
                side. Defaults to 300.
            projection (string, optional): The map projection. Accepted
                values are ``ortho``, corresponding to an orthographic
                projection (as seen on the sky), ``rect``, corresponding
                to an equirectangular latitude-longitude projection,
                and ``moll``, corresponding to a Mollweide equal-area
                projection. Defaults to ``ortho``.

        """
        projection = get_projection(projection)
        if projection == STARRY_RECTANGULAR_PROJECTION:
            lat, lon = self.ops.compute_rect_grid(res)[0]
        elif projection == STARRY_MOLLWEIDE_PROJECTION:
            lat, lon = self.ops.compute_moll_grid(res)[0]
        else:
            latlon = self.ops.compute_ortho_grid_inc_obl(
                res, self._inc, self._obl
            )[0]
            lat = latlon[0]
            lon = latlon[1]
        return (
            self._math.reshape(lat, (res, res)) / self._angle_factor,
            self._math.reshape(lon, (res, res)) / self._angle_factor,
        )

    def load(
        self,
        image,
        extent=(-180, 180, -90, 90),
        smoothing=None,
        fac=1.0,
        eps=1e-12,
        force_psd=False,
        **kwargs
    ):
        """Load an image or ndarray.

        This routine performs a simple spherical harmonic transform (SHT)
        to compute the spherical harmonic expansion corresponding to
        an input image file or ``numpy`` array on a lat-lon grid.
        The resulting coefficients are ingested into the map.

        Args:
            image: A path to an image PNG file or a two-dimensional ``numpy``
                array on a latitude-longitude grid.
            extent (tuple, optional): The lat-lon values corresponding to the
                edges of the image in degrees, ``(lat0, lat1, lon0, lon1)``.
                Default is ``(-180, 180, -90, 90)``.
            smoothing (float, optional): Gaussian smoothing strength.
                Increase this value to suppress ringing or explicitly set to zero to
                disable smoothing. Default is ``1/self.ydeg``.
            fac (float, optional): Factor by which to oversample the image
                when applying the SHT. Default is ``1.0``. Increase this
                number for higher fidelity (at the expense of increased
                computational time).
            eps (float, optional): Regularization strength for the spherical
                harmonic transform. Default is ``1e-12``.
            force_psd (bool, optional): Force the map to be positive
                semi-definite? Default is False.
            kwargs (optional): Any other kwargs passed directly to
                :py:meth:`minimize` (only if ``psd`` is True).
        """
        # Not implemented for spectral
        self._no_spectral()

        # Function to get tensor values
        get_val = evaluator(**kwargs)

        # Is this a file name?
        if type(image) is str:
            # Get the full path
            if not os.path.exists(image):
                image = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "img", image
                )
                if not image.endswith(".png"):
                    image += ".png"
                if not os.path.exists(image):
                    raise ValueError("File not found: %s." % image)

            # Load the image into an ndarray
            image = plt.imread(image)

            # If it's an integer, normalize to [0-1]
            # (if it's a float, it's already normalized)
            if np.issubdtype(image.dtype, np.integer):
                image = image / 255.0

            # Convert to grayscale
            if len(image.shape) == 3:
                image = np.mean(image[:, :, :3], axis=2)
            elif len(image.shape) == 4:
                # ignore any transparency
                image = np.mean(image[:, :, :3], axis=(2, 3))

            # Re-orient
            image = np.flipud(image)

        # Downsample the image to Nyquist-ish
        factor = fac * 4 * self.ydeg / image.shape[1]
        if factor < 1:
            image = zoom(image, factor, mode="nearest")

        # Get the lat-lon grid
        nlat, nlon = image.shape
        lon = np.linspace(extent[0], extent[1], nlon) * np.pi / 180
        lat = np.linspace(extent[2], extent[3], nlat) * np.pi / 180
        lon, lat = np.meshgrid(lon, lat)
        lon = lon.flatten()
        lat = lat.flatten()

        # Compute the cos(lat)-weighted SHT
        w = np.cos(lat)
        P = self.ops.P(lat, lon)
        PTSinv = P.T * (w ** 2)[None, :]
        Q = np.linalg.solve(PTSinv @ P + eps * np.eye(P.shape[1]), PTSinv)
        if smoothing is None:
            smoothing = 1.0 / self.ydeg
        if smoothing > 0:
            l = np.concatenate(
                [np.repeat(l, 2 * l + 1) for l in range(self.ydeg + 1)]
            )
            s = np.exp(-0.5 * l * (l + 1) * smoothing ** 2)
            Q *= s[:, None]

        # The Ylm coefficients are just a linear op on the image
        y = Q @ image.flatten()

        # Enforce the starry 1/pi normalization
        y /= np.pi

        # Ingest the coefficients
        self._y = self._math.cast(y / y[0])
        self.amp = self._math.cast(y[0] * np.pi)

        # Note: reflected light maps are normalized a little differently
        if self.__props__["reflected"]:
            self.amp /= np.pi

        # Ensure positive semi-definite?
        if force_psd:

            # Find the minimum
            _, _, I = self.minimize(**kwargs)
            if self.lazy:
                I = get_val(I)

            # Scale the coeffs?
            if I < 0:
                fac = self.amp / (self.amp - np.pi * I)
                if self.lazy:
                    self._y *= fac
                    self._y = self.ops.set_vector(self._y, 0, 1.0)
                else:
                    self._y[1:] *= fac

    def rotate(self, axis, theta):
        """Rotate the current map vector an angle ``theta`` about ``axis``.

        Args:
            axis (vector): The axis about which to rotate the map.
            theta (scalar): The angle of (counter-clockwise) rotation.
        """
        axis = self._math.cast(axis)
        axis /= self._math.sqrt(self._math.sum(axis ** 2))
        # Note that we rotate by -theta since
        # this is the *RHS* rotation operator
        y = self.ops.dotR(
            self._math.transpose(
                self._math.reshape(
                    self.y, (-1, 1 if self.nw is None else self.nw)
                )
            ),
            axis[0],
            axis[1],
            axis[2],
            -self._math.cast(theta * self._angle_factor),
        )
        if self.nw is None:
            self._y = y[0]
        else:
            self._y = self._math.transpose(y)

    def spot(self, *, contrast=1.0, radius=None, lat=0.0, lon=0.0, **kwargs):
        r"""Add the expansion of a circular spot to the map.

        This function adds a spot whose functional form is a top
        hat in :math:`\Delta\theta`, the
        angular separation between the center of the spot and another
        point on the surface. The spot intensity is controlled by the
        parameter ``contrast``, defined as the fractional change in the
        intensity at the center of the spot.

        Args:
            contrast (scalar or vector, optional): The contrast of the spot.
                This is equal to the fractional change in the intensity of the
                map at the *center* of the spot relative to the baseline intensity
                of an unspotted map. If the map has more than one
                wavelength bin, this must be a vector of length equal to the
                number of wavelength bins. Positive values of the contrast
                result in dark spots; negative values result in bright
                spots. Default is ``1.0``, corresponding to a spot with
                central intensity close to zero.
            radius (scalar, optional): The angular radius of the spot in
                units of :py:attr:`angle_unit`. Defaults to ``20.0`` degrees.
            lat (scalar, optional): The latitude of the spot in units of
                :py:attr:`angle_unit`. Defaults to ``0.0``.
            lon (scalar, optional): The longitude of the spot in units of
                :py:attr:`angle_unit`. Defaults to ``0.0``.

        .. note::

            Keep in mind that things are normalized in ``starry`` such that
            the disk-integrated *flux* (not the *intensity*!)
            of an unspotted body is unity. The default intensity of an
            unspotted map is ``1.0 / np.pi`` everywhere (this ensures the
            integral over the unit disk is unity).
            So when you instantiate a map and add a spot of contrast ``c``,
            you'll see that the intensity at the center is actually
            ``(1 - c) / np.pi``. This is expected behavior, since that's
            a factor of ``1 - c`` smaller than the baseline intensity.

        .. note::

            This function computes the spherical harmonic expansion of a
            circular spot with uniform contrast. At finite spherical
            harmonic degree, this will return an *approximation* that
            may be subject to ringing. Users can control the amount of
            ringing and the smoothness of the spot profile (see below).
            In general, however, at a given spherical harmonic degree
            ``ydeg``, there is always minimum spot radius that can be
            modeled well. For ``ydeg = 15``, for instance, that radius
            is about ``10`` degrees. Attempting to add a spot smaller
            than this will in general result in a large amount of ringing and
            a smaller contrast than desired.

        There are a few additional under-the-hood keywords
        that control the behavior of the spot expansion. These are

        Args:
            spot_pts (int, optional): The number of points in the expansion
                of the (1-dimensional) spot profile. Default is ``1000``.
            spot_eps (float, optional): Regularization parameter in the
                expansion. Default is ``1e-9``.
            spot_smoothing (float, optional): Standard deviation of the
                Gaussian smoothing applied to the spot to suppress
                ringing (unitless). Default is ``2.0 / self.ydeg``.
            spot_fac (float, optional): Parameter controlling the smoothness
                of the spot profile. Increasing this parameter increases
                the steepness of the profile (which approaches a top hat
                as ``spot_fac -> inf``). Decreasing it results in a smoother
                sigmoidal function. Default is ``300``. Changing this
                parameter is not recommended; change ``spot_smoothing``
                instead.

        .. note::

            These last four parameters are cached. That means that
            changing their value in a call to ``spot`` will result in
            all future calls to ``spot`` "remembering" those settings,
            unless you change them back!

        """
        # Set up (if kwargs changed)
        self.ops._spot_setup(**kwargs)

        # Check inputs
        if radius is None:
            radius = self._math.cast(20 * np.pi / 180)
        else:
            radius = self._math.cast(radius) * self._angle_factor
        lat = self._math.cast(lat) * self._angle_factor
        lon = self._math.cast(lon) * self._angle_factor
        if self.nw is None:
            contrast = self._math.cast(contrast)
        else:
            contrast = self._math.cast(contrast) * self._math.ones(self.nw)

        # Add the spot to the map
        y_spot = self.ops.spot(contrast, radius, lat, lon)
        x = self._amp * self._y + y_spot
        self._amp = x[0]
        self._y = x / x[0]

    def minimize(self, oversample=1, ntries=1, bounds=None, return_info=False):
        """Find the global (optionally local) minimum of the map intensity.

        Args:
            oversample (int): Factor by which to oversample the initial
                grid on which the brute force search is performed. Default 1.
            ntries (int): Number of times the nonlinear minimizer is called.
                Default 1.
            return_info (bool): Return the info from the minimization call?
                Default is False.
            bounds (tuple): Return map minimum in a certain latitude/longitude
                range, for example bounds=((0, 90), (0, 180)). Default None.

        Returns:
            A tuple of the latitude, longitude, and the value of the intensity \
            at the minimum. If ``return_info`` is True, also returns the detailed \
            solver information.
        """
        # Not implemented for spectral
        self._no_spectral()

        self.ops._minimize.setup(
            oversample=oversample, ntries=ntries, bounds=bounds
        )
        lat, lon, I = self.ops.get_minimum(self.y)
        if return_info:  # pragma: no cover
            return (
                lat / self._angle_factor,
                lon / self._angle_factor,
                self.amp * I,
                self.ops._minimize.result,
            )
        else:
            return (
                lat / self._angle_factor,
                lon / self._angle_factor,
                self.amp * I,
            )

    def sht_matrix(
        self,
        inverse=False,
        return_grid=False,
        smoothing=None,
        oversample=2,
        lam=1e-6,
    ):
        """
        Return the Spherical Harmonic Transform (SHT) matrix.

        This matrix dots into a vector of pixel intensities defined on
        a set of latitude-longitude points, resulting in a vector of spherical
        harmonic coefficients that best approximates the image.

        This can be useful for transforming between the spherical harmonic and
        pixel representations of the surface map, such as when specifying
        priors during inference or optimization.
        For example, one application is when one wishes to sample in
        the pixel intensities ``p`` instead of the spherical harmonic coefficients
        ``y``. In this case,
        one must compute the spherical harmonic coefficients ``y`` from
        the vector of pixel intensities ``p`` so that
        ``starry`` can compute the model for the flux:

            .. code-block::python

                A = map.sht_matrix()
                y = np.dot(A, p)
                map[:, :] = y

        .. note::

            This method is a thin wrapper of the ``get_pixel_transforms`` method.

        Args:
            inverse (bool, optional). If True, returns the inverse transform,
                which transforms from spherical harmonic coefficients to
                pixels. Default is False.
            return_grid (bool, optional). If True, also returns an array of
                shape ``(npix, 2)`` corresponding to the latitude-longitude
                points (in units of :py:attr:`angle_unit`) on which the SHT is
                evaluated. Default is False.
            smoothing (float, optional): Gaussian smoothing strength.
                Increase this value to suppress ringing (forward SHT only) or
                explicitly set to zero to disable smoothing. Default is
                ``2/self.ydeg``.
            oversample (int, optional): Factor by which to oversample the
                pixelization grid. Default `2`.
            lam (float, optional): Regularization parameter for the inverse
                pixel transform. Default `1e-6`.

        Returns:
            A matrix of shape (:py:attr:`Ny`, ``npix``) or
            (:py:attr:`npix`, ``Ny``) (if ``inverse`` is True), where ``npix``
            is the number of pixels on the grid. This number is determined
            from the degree of the map and the ``oversample`` keyword. If
            ``return_grid`` is True, also returns the latitude-longitude points
            (in units of :py:attr:`angle_unit`) on which the SHT is
            evaluated, a matrix of shape ``(npix, 2)``.

        """
        lat, lon, ISHT, SHT, _, _ = self.get_pixel_transforms(
            oversample=oversample, lam=lam
        )
        if inverse:
            matrix = ISHT
        else:
            matrix = SHT
            if smoothing is None:
                smoothing = 2.0 / self.ydeg
            if smoothing > 0:
                l = np.concatenate(
                    [np.repeat(l, 2 * l + 1) for l in range(self.ydeg + 1)]
                )
                s = np.exp(-0.5 * l * (l + 1) * smoothing ** 2)
                matrix *= s[:, None]
        if return_grid:
            grid = np.vstack((lat, lon)).T
            return matrix, grid
        else:
            return matrix

    def get_pixel_transforms(self, oversample=2, lam=1e-6, eps=1e-6):
        """
        Return several linear operators for pixel transformations.

        Args:
            oversample (int): Factor by which to oversample the pixelization
                grid. Default 2.
            lam (float): Regularization parameter for the inverse pixel transform.
                Default `1e-6`.
            eps (float): Regularization parameter for the derivative transforms.
                Default `1e-6`.

        Returns:
            The tuple `(lat, lon, Y2P, P2Y, Dx, Dy)`.

        The transforms returned by this method can be used to easily convert back
        and forth between spherical harmonic coefficients and intensities on a
        discrete pixelized grid. Projections onto pixels are performed on an
        equal-area Mollweide grid, so these transforms are useful for applying
        priors on the pixel intensities, for instance.

        The `lat` and `lon` arrays correspond to the latitude and longitude of
        each of the points used in the transform (in units of `angle_unit`).

        The `Y2P` matrix is an operator that transforms from spherical harmonic
        coefficients `y` to pixels `p` on a Mollweide grid:

        .. code-block:: python

            p = Y2P @ y

        The `P2Y` matrix is the (pseudo-)inverse of that operator:

        .. code-block:: python

            y = P2Y @ p

        Finally, the `Dx` and `Dy` operators transform a pixel representation
        of the map `p` to the derivative of `p` with respect to longitude and
        latitude, respectively:

        .. code-block:: python

            dpdlon = Dx @ p
            dpdlat = Dy @ p

        By combining these operators, one can differentiate the spherical
        harmonic expansion with respect to latitude and longitude, if desired:

            dydlon = P2Y @ Dx @ Y2P @ y
            dydlat = P2Y @ Dy @ Y2P @ y

        These derivatives could be useful for implementing total-variation-reducing
        regularization, for instance.

        .. warning::

            This is an experimental feature.

        """
        # Prevent undersampling for ydeg = 1
        if self.ydeg <= 1:
            self.oversample = max(oversample, 3)

        # Target number of pixels
        npix = oversample * (self.ydeg + 1) ** 2
        Ny = int(np.sqrt(npix * np.pi / 4.0))
        Nx = 2 * Ny
        y, x = np.meshgrid(
            np.sqrt(2) * np.linspace(-1, 1, Ny),
            2 * np.sqrt(2) * np.linspace(-1, 1, Nx),
        )
        x = x.flatten()
        y = y.flatten()

        # Remove off-grid points
        a = np.sqrt(2)
        b = 2 * np.sqrt(2)
        idx = (y / a) ** 2 + (x / b) ** 2 <= 1
        y = y[idx]
        x = x[idx]

        # https://en.wikipedia.org/wiki/Mollweide_projection
        theta = np.arcsin(y / np.sqrt(2))
        lat = np.arcsin((2 * theta + np.sin(2 * theta)) / np.pi)
        lon0 = 3 * np.pi / 2
        lon = lon0 + np.pi * x / (2 * np.sqrt(2) * np.cos(theta))

        # Add points at the poles if not included
        if -np.pi / 2 not in lat:
            lat = np.append(lat, [-np.pi / 2])
            lon = np.append(lon, [1.5 * np.pi])
        if  np.pi / 2 not in lat:
            lat = np.append(lat, [ np.pi / 2])
            lon = np.append(lon, [1.5 * np.pi])
        npix = len(lat)
        npix = len(lat)

        # Back to Cartesian, this time on the *sky*
        x = np.reshape(np.cos(lat) * np.cos(lon), [1, -1])
        y = np.reshape(np.cos(lat) * np.sin(lon), [1, -1])
        z = np.reshape(np.sin(lat), [1, -1])
        R = self.ops.RAxisAngle(
            np.array([1.0, 0.0, 0.0]), np.array(-np.pi / 2)
        )
        x, y, z = np.dot(R, np.concatenate((x, y, z)))
        x = x.reshape(-1)
        y = y.reshape(-1)
        z = z.reshape(-1)

        # Flatten and fix the longitude offset, then sort by latitude
        lat = lat.reshape(-1)
        lon = (lon - 1.5 * np.pi).reshape(-1)
        idx = np.lexsort([lon, lat])
        lat = lat[idx]
        lon = lon[idx]
        x = x[idx]
        y = y[idx]
        z = z[idx]

        # Get the forward pixel transform
        pT = self.ops.pT(x, y, z)[:, : (self.ydeg + 1) ** 2]
        Y2P = pT * self.ops._c_ops.A1

        # Get the inverse pixel transform
        P2Y = np.linalg.solve(Y2P.T.dot(Y2P) + lam * np.eye(self.Ny), Y2P.T)

        # Construct the differentiation operators
        Dx = np.zeros((npix, npix))
        Dy = np.zeros((npix, npix))
        for i in range(npix):

            # Get the relative x, y coords of the 8 closest points
            y_ = (lat - lat[i]) * np.pi / 180
            x_ = (
                np.cos(0.5 * (lat + lat[i]) * np.pi / 180)
                * (lon - lon[i])
                * np.pi
                / 180
            )
            idx = np.argsort(x_ ** 2 + y_ ** 2)
            x = x_[idx[:8]]
            y = y_[idx[:8]]

            # Require at least one point to be at a different latitude
            j = np.argmax(np.abs(lat[idx] - lat[idx[0]]) > 1e-4)
            if j >= 8:
                # TODO: untested!
                x[-1] = x_[idx[j]]
                y[-1] = y_[idx[j]]

            # Construct the design matrix that gives us
            # the coefficients of the polynomial fit
            # centered on the current point
            X = np.vstack(
                (
                    np.ones(8),
                    x,
                    y,
                    x ** 2,
                    x * y,
                    y ** 2,
                    x ** 3,
                    x ** 2 * y,
                    x * y ** 2,
                    y ** 3,
                )
            ).T
            A = np.linalg.solve(X.T.dot(X) + eps * np.eye(10), X.T)

            # Since we're centered at the origin, the derivatives
            # are just the coefficients of the linear terms.
            Dx[i, idx[:8]] = A[1]
            Dy[i, idx[:8]] = A[2]

        return (
            lat / self._angle_factor,
            lon / self._angle_factor,
            Y2P,
            P2Y,
            Dx * self._angle_factor,
            Dy * self._angle_factor,
        )


class LimbDarkenedBase(object):
    """The ``starry`` map class for purely limb-darkened maps.

    This class handles light curves of purely limb-darkened objects in
    emitted light.

    .. note::
        Instantiate this class by calling :py:func:`starry.Map` with
        ``ydeg`` set to zero and both ``rv`` and ``reflected`` set to False.
    """

    _ops_class_ = OpsLD

    def _render_greedy(self, **kwargs):
        get_val = evaluator(**kwargs)
        amp = get_val(self.amp).reshape(-1, 1, 1)
        return amp.reshape(-1, 1, 1) * self.ops.render_ld(
            kwargs.get("res", 300), get_val(self._u)
        )

    def _get_projection(self, **kwargs):
        projection = get_projection(kwargs.get("projection", "ortho"))
        assert (
            projection == STARRY_ORTHOGRAPHIC_PROJECTION
        ), "Only orthographic projection is supported for limb-darkened maps."
        return projection

    def _get_ortho_latitude_lines(self, **kwargs):
        return get_ortho_latitude_lines()

    def _get_ortho_longitude_lines(self, i=0, **kwargs):
        return get_ortho_longitude_lines()

    def _updatefig(i):
        return ()

    def _get_flux_kwargs(self, kwargs):
        xo = kwargs.get("xo", 0.0)
        yo = kwargs.get("yo", 0.0)
        zo = kwargs.get("zo", 1.0)
        ro = kwargs.get("ro", 0.0)
        xo, yo, zo = self._math.vectorize(xo, yo, zo)
        xo, yo, zo, ro = self._math.cast(xo, yo, zo, ro)
        return xo, yo, zo, ro

    def flux(self, **kwargs):
        """
        Compute and return the light curve.

        Args:
            xo (scalar or vector, optional): x coordinate of the occultor
                relative to this body in units of this body's radius.
            yo (scalar or vector, optional): y coordinate of the occultor
                relative to this body in units of this body's radius.
            zo (scalar or vector, optional): z coordinate of the occultor
                relative to this body in units of this body's radius.
            ro (scalar, optional): Radius of the occultor in units of
                this body's radius.
        """
        # Orbital kwargs
        xo, yo, zo, ro = self._get_flux_kwargs(kwargs)

        # Compute & return
        return self.amp * self.ops.flux(xo, yo, zo, ro, self._u)

    def intensity(self, mu=None, x=None, y=None):
        r"""
        Compute and return the intensity of the map.

        Args:
            mu (scalar or vector, optional): the radial parameter :math:`\mu`,
                equal to the cosine of the angle between the line of sight and
                the normal to the surface. Default is None.
            x (scalar or vector, optional): the Cartesian x position on the
                surface in units of the body's radius. Default is None.
            y (scalar or vector, optional): the Cartesian y position on the
                surface in units of the body's radius. Default is None.

        .. note::
            Users must provide either `mu` **or** `x` and `y`.
        """
        # Get the Cartesian points
        if mu is not None:
            mu = self._math.vectorize(self._math.cast(mu))
            assert (
                x is None and y is None
            ), "Please provide either `mu` or `x` and `y`, but not both."
        else:
            assert (
                x is not None and y is not None
            ), "Please provide either `mu` or `x` and `y`."
            x, y = self._math.vectorize(*self._math.cast(x, y))
            mu = (1 - x ** 2 - y ** 2) ** 0.5

        # Compute & return
        return self.amp * self.ops.intensity(mu, self._u)

    def render(self, res=300):
        """Compute and return the intensity of the map on a grid.

        Returns an image of shape ``(res, res)``.

        Args:
            res (int, optional): The resolution of the map in pixels on a
                side. Defaults to 300.
        """
        # Multiple frames?
        if self.nw is not None:
            animated = True
        else:
            animated = False

        # Compute
        image = self.amp * self.ops.render_ld(res, self._u)

        # Squeeze?
        if animated:
            return image
        else:
            return self._math.reshape(image, [res, res])


class RVBase(object):
    """The radial velocity ``starry`` map class.

    This class handles velocity-weighted intensities for use in
    Rossiter-McLaughlin effect investigations. It has all the same
    attributes and methods as :py:class:`starry.maps.YlmBase`, with the
    additions and modifications listed below.

    All velocities are in meters per second, unless otherwise
    specified via the attribute :py:attr:`_velocity_unit``.

    .. note::
        Instantiate this class by calling :py:func:`starry.Map` with
        ``ydeg > 0`` and ``rv`` set to True.
    """

    _ops_class_ = OpsRV

    def _get_norm(self, image, **kwargs):
        norm = kwargs.get("norm", None)
        if norm is None:
            vmin = np.nanmin(image)
            vmax = np.nanmax(image)
            if np.abs(vmin - vmax) < 1e-9:
                vmin -= 1e-9
                vmax += 1e-9
            try:
                norm = colors.TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax)
            except (AttributeError, ValueError):  # pragma: no cover
                # TwoSlopeNorm was introduced in matplotlib 3.2
                norm = colors.Normalize(vmin=vmin, vmax=vmax)
        else:
            return norm

    def reset(self, **kwargs):
        self.velocity_unit = kwargs.get("velocity_unit", units.m / units.s)
        self.veq = kwargs.get("veq", 0.0)
        self.alpha = kwargs.get("alpha", 0.0)
        super(RVBase, self).reset(**kwargs)

    @property
    def velocity_unit(self):
        """An ``astropy.units`` unit defining the velocity metric for this map."""
        return self._velocity_unit

    @velocity_unit.setter
    def velocity_unit(self, value):
        assert value.physical_type == "speed"
        self._velocity_unit = value
        self._velocity_factor = value.in_units(units.m / units.s)

    @property
    def alpha(self):
        """The rotational shear coefficient, a number in the range ``[0, 1]``.

        The parameter :math:`\\alpha` is used to model linear differential
        rotation. The angular velocity at a given latitude :math:`\\theta`
        is

        :math:`\\omega = \\omega_{eq}(1 - \\alpha \\sin^2\\theta)`

        where :math:`\\omega_{eq}` is the equatorial angular velocity of
        the object.

        """
        return self._alpha

    @alpha.setter
    def alpha(self, value):
        self._alpha = self._math.cast(value)

    @property
    def veq(self):
        """The equatorial velocity of the body in units of :py:attr:`velocity_unit`.

        .. warning::
            If this map is associated with a :py:class:`starry.Body`
            instance in a Keplerian system, changing the body's
            radius and rotation period does not currently affect this
            value. The user must explicitly change this value to affect
            the map's radial velocity.

        """
        return self._veq / self._velocity_factor

    @veq.setter
    def veq(self, value):
        self._veq = self._math.cast(value) * self._velocity_factor

    def _unset_RV_filter(self):
        f = np.zeros(self.Nf)
        f[0] = np.pi
        self._f = self._math.cast(f)

    def _set_RV_filter(self):
        self._f = self.ops.compute_rv_filter(
            self._inc, self._obl, self._veq, self._alpha
        )

    def rv(self, **kwargs):
        """Compute the net radial velocity one would measure from the object.

        The radial velocity is computed as the ratio

            :math:`\\Delta RV = \\frac{\\int Iv \\mathrm{d}A}{\\int I \\mathrm{d}A}`

        where both integrals are taken over the visible portion of the
        projected disk. :math:`I` is the intensity field (described by the
        spherical harmonic and limb darkening coefficients) and :math:`v`
        is the radial velocity field (computed based on the equatorial velocity
        of the star, its orientation, etc.)

        Args:
            xo (scalar or vector, optional): x coordinate of the occultor
                relative to this body in units of this body's radius.
            yo (scalar or vector, optional): y coordinate of the occultor
                relative to this body in units of this body's radius.
            zo (scalar or vector, optional): z coordinate of the occultor
                relative to this body in units of this body's radius.
            ro (scalar, optional): Radius of the occultor in units of
                this body's radius.
            theta (scalar or vector, optional): Angular phase of the body
                in units of :py:attr:`angle_unit`.

        Returns:
            The radial velocity in units of :py:attr:`velocity_unit`.

        """
        # Orbital kwargs
        theta, xo, yo, zo, ro = self._get_flux_kwargs(kwargs)

        # Compute
        return self.ops.rv(
            theta,
            xo,
            yo,
            zo,
            ro,
            self._inc,
            self._obl,
            self._y,
            self._u,
            self._veq,
            self._alpha,
        )

    def intensity(self, **kwargs):
        """
        Compute and return the intensity of the map.

        Args:
            lat (scalar or vector, optional): latitude at which to evaluate
                the intensity in units of :py:attr:`angle_unit`.
            lon (scalar or vector, optional): longitude at which to evaluate
                the intensity in units of :py:attr:`angle_unit`.
            rv (bool, optional): If True, computes the velocity-weighted
                intensity instead. Defaults to True.
            theta (scalar, optional): For differentially rotating maps only,
                the angular phase at which to evaluate the intensity.
                Default 0.
            limbdarken (bool, optional): Apply limb darkening
                (only if :py:attr:`udeg` > 0)? Default True.

        """
        # Compute the velocity-weighted intensity if `rv==True`
        rv = kwargs.get("rv", True)
        if rv:
            self._set_RV_filter()
        res = super(RVBase, self).intensity(**kwargs)
        if rv:
            self._unset_RV_filter()
        return res

    def render(self, **kwargs):
        """
        Compute and return the intensity of the map on a grid.

        Returns an image of shape ``(res, res)``, unless ``theta`` is a vector,
        in which case returns an array of shape ``(nframes, res, res)``, where
        ``nframes`` is the number of values of ``theta``. However, if this is
        a spectral map, ``nframes`` is the number of wavelength bins and
        ``theta`` must be a scalar.

        Args:
            res (int, optional): The resolution of the map in pixels on a
                side. Defaults to 300.
            projection (string, optional): The map projection. Accepted
                values are ``ortho``, corresponding to an orthographic
                projection (as seen on the sky), ``rect``, corresponding
                to an equirectangular latitude-longitude projection,
                and ``moll``, corresponding to a Mollweide equal-area
                projection. Defaults to ``ortho``.
            theta (scalar or vector, optional): The map rotation phase in
                units of :py:attr:`angle_unit`. If this is a vector, an
                animation is generated. Defaults to ``0.0``.
            rv (bool, optional): If True, computes the velocity-weighted
                intensity instead. Defaults to True.
        """
        # Render the velocity map if `rv==True`
        # Override the `projection` kwarg if we're
        # plotting the radial velocity.
        rv = kwargs.pop("rv", True)
        if rv:
            kwargs.pop("projection", None)
            self._set_RV_filter()
        res = super(RVBase, self).render(**kwargs)
        if rv:
            self._unset_RV_filter()
        return res

    def show(self, rv=True, **kwargs):
        # Show the velocity map if `rv==True`
        # Override some kwargs if we're
        # plotting the radial velocity.
        if rv:
            kwargs.pop("projection", None)
            self._set_RV_filter()
            kwargs["cmap"] = kwargs.get("cmap", "RdBu_r")
        res = super(RVBase, self).show(rv=rv, **kwargs)
        if rv:
            self._unset_RV_filter()
        return res


class ReflectedBase(object):
    """The reflected light ``starry`` map class.

    This class handles light curves and phase curves of objects viewed
    in reflected light. It has all the same attributes and methods as
    :py:class:`starry.maps.YlmBase`, with the
    additions and modifications listed below.

    The spherical harmonic coefficients of a map in reflected light are
    an expansion of the object's *spherical albedo* (instead of its emissivity,
    in the default case). The body is assumed to be a spherical,
    non-uniform Lambertian scatterer.

    By default, the illumination source is assumed to be a point source for
    the purposes of computing the illumination profile on the surface of the
    body and as a spherical source of finite extent for the purposes of
    modeling occultations. The point source approximation can be relaxed by
    changing the `source_npts` keyword when instantiating the map. This may
    be important for modeling very short-period exoplanets.

    The ``xs``, ``ys``, and ``zs`` parameters in several of the methods below
    specify the position of the illumination source in units of this body's
    radius. The flux returned by the :py:meth:`flux` method is normalized to
    that which would be measured from a perfect Lambertian sphere of unit radius
    illuminated by a source whose flux at the observer is unity.

    The ``amp`` parameter controls the overall scaling of the body's flux.
    The default value is unity, which corresponds to a perfect Lambertian
    sphere, for which ``q = 3 / 2``, where ``q`` is the ratio of the body's
    spherical albedo to its geometric albedo. Different values of ``q`` can
    be obtained by changing ``amp`` accordingly.

    .. note::
        Instantiate this class by calling
        :py:func:`starry.Map` with ``ydeg > 0`` and ``reflected`` set to True.
    """

    _ops_class_ = OpsReflected

    def reset(self, **kwargs):
        self.roughness = kwargs.get("roughness", self._math.cast(0.0))
        super(ReflectedBase, self).reset(**kwargs)

    @property
    def source_npts(self):
        """
        The number of points used when approximating finite illumination
        source size. This quantity must be set when instantiating the map.

        """
        return int(self.__props__["source_npts"])

    @property
    def roughness(self):
        """
        The Oren-Nayar (1994) surface roughness parameter, `sigma`,
        in units of :py:attr:`angle_unit`.

        """
        return self._sigr / self._angle_factor

    @roughness.setter
    def roughness(self, value):
        self._sigr = self._math.cast(value) * self._angle_factor

    def _get_flux_kwargs(self, kwargs):
        xo = kwargs.get("xo", 0.0)
        yo = kwargs.get("yo", 0.0)
        zo = kwargs.get("zo", 1.0)
        ro = kwargs.get("ro", 0.0)
        xs = kwargs.get("xs", 0.0)
        ys = kwargs.get("ys", 0.0)
        zs = kwargs.get("zs", 1.0)
        Rs = kwargs.get("rs", 0.0)
        theta = kwargs.get("theta", 0.0)
        theta, xs, ys, zs, xo, yo, zo = self._math.vectorize(
            theta, xs, ys, zs, xo, yo, zo
        )
        theta, xs, ys, zs, xo, yo, zo, ro, Rs = self._math.cast(
            theta, xs, ys, zs, xo, yo, zo, ro, Rs
        )
        theta *= self._angle_factor
        return theta, xs, ys, zs, Rs, xo, yo, zo, ro

    def design_matrix(self, **kwargs):
        r"""
        Compute and return the light curve design matrix, :math:`A`.

        This matrix is used to compute the flux :math:`f` from a vector of spherical
        harmonic coefficients :math:`y` and the map amplitude :math:`a`:
        :math:`f = a A y`.

        Args:
            xs (scalar or vector, optional): x coordinate of the illumination
                source relative to this body in units of this body's radius.
            ys (scalar or vector, optional): y coordinate of the illumination
                source relative to this body in units of this body's radius.
            zs (scalar or vector, optional): z coordinate of the illumination
                source relative to this body in units of this body's radius.
            rs (scalar, optional): radius of the illumination source in units
                of this body's radius.
            xo (scalar or vector, optional): x coordinate of the occultor
                relative to this body in units of this body's radius.
            yo (scalar or vector, optional): y coordinate of the occultor
                relative to this body in units of this body's radius.
            zo (scalar or vector, optional): z coordinate of the occultor
                relative to this body in units of this body's radius.
            ro (scalar, optional): Radius of the occultor in units of
                this body's radius.
            theta (scalar or vector, optional): Angular phase of the body
                in units of :py:attr:`angle_unit`.

        """
        # Orbital kwargs
        theta, xs, ys, zs, Rs, xo, yo, zo, ro = self._get_flux_kwargs(kwargs)

        # Compute & return
        return self.ops.X(
            theta,
            xs,
            ys,
            zs,
            Rs,
            xo,
            yo,
            zo,
            ro,
            self._inc,
            self._obl,
            self._u,
            self._f,
            self._sigr,
        )

    def flux(self, **kwargs):
        """
        Compute and return the reflected flux from the map.

        Args:
            xs (scalar or vector, optional): x coordinate of the illumination
                source relative to this body in units of this body's radius.
            ys (scalar or vector, optional): y coordinate of the illumination
                source relative to this body in units of this body's radius.
            zs (scalar or vector, optional): z coordinate of the illumination
                source relative to this body in units of this body's radius.
            rs (scalar, optional): radius of the illumination source in units
                of this body's radius.
            xo (scalar or vector, optional): x coordinate of the occultor
                relative to this body in units of this body's radius.
            yo (scalar or vector, optional): y coordinate of the occultor
                relative to this body in units of this body's radius.
            zo (scalar or vector, optional): z coordinate of the occultor
                relative to this body in units of this body's radius.
            ro (scalar, optional): Radius of the occultor in units of
                this body's radius.
            theta (scalar or vector, optional): Angular phase of the body
                in units of :py:attr:`angle_unit`.
            integrated (bool, optional): If True, dots the flux with the
                amplitude. Default False, in which case this returns a
                2d array (wavelength-dependent maps only).

        """
        # Orbital kwargs
        theta, xs, ys, zs, Rs, xo, yo, zo, ro = self._get_flux_kwargs(kwargs)

        # Compute & return
        flux = self.ops.flux(
            theta,
            xs,
            ys,
            zs,
            Rs,
            xo,
            yo,
            zo,
            ro,
            self._inc,
            self._obl,
            self._y,
            self._u,
            self._f,
            self._sigr,
        )

        if kwargs.get("integrated", False):
            return self._math.dot(flux, self.amp)
        else:
            return self.amp * flux

    def intensity(
        self,
        lat=0,
        lon=0,
        xs=0,
        ys=0,
        zs=1,
        rs=0,
        on94_exact=False,
        illuminate=True,
        **kwargs
    ):
        """
        Compute and return the intensity of the map.

        Args:
            lat (scalar or vector, optional): latitude at which to evaluate
                the intensity in units of :py:attr:`angle_unit`.
            lon (scalar or vector, optional): longitude at which to evaluate
                the intensity in units of :py:attr:`angle_unit`.
            xs (scalar or vector, optional): x coordinate of the illumination
                source relative to this body in units of this body's radius.
            ys (scalar or vector, optional): y coordinate of the illumination
                source relative to this body in units of this body's radius.
            zs (scalar or vector, optional): z coordinate of the illumination
                source relative to this body in units of this body's radius.
            rs (scalar, optional): radius of the illumination source in units
                of this body's radius.
            theta (scalar, optional): For differentially rotating maps only,
                the angular phase at which to evaluate the intensity.
                Default 0.
            limbdarken (bool, optional): Apply limb darkening
                (only if :py:attr:`udeg` > 0)? Default True.
        """
        # Get the Cartesian points
        lat, lon = self._math.vectorize(*self._math.cast(lat, lon))
        lat *= self._angle_factor
        lon *= self._angle_factor

        # Get the source position
        xs, ys, zs = self._math.vectorize(*self._math.cast(xs, ys, zs))
        Rs = self._math.cast(rs)

        # Get the amplitude
        if self.nw is None:
            amp = self.amp
        else:
            # The intensity has shape `(nsurf_pts, nw, nsource_pts)`
            # so we must reshape `amp` to take the product correctly
            amp = self.amp[np.newaxis, :, np.newaxis]

        # If differentially rotating, allow a `theta` keyword
        theta = self._math.cast(kwargs.get("theta", 0.0))
        theta *= self._angle_factor

        # If limb-darkened, allow a `limbdarken` keyword
        if self.udeg > 0:
            ld = np.array(True)
        else:
            ld = np.array(False)

        # Exact Oren & Nayar intensity?
        on94_exact = int(on94_exact)

        # Illuminate the map? If False, returns the *albedo*
        illuminate = int(illuminate)

        # Compute & return
        return amp * self.ops.intensity(
            lat,
            lon,
            self._y,
            self._u,
            self._f,
            xs,
            ys,
            zs,
            Rs,
            theta,
            ld,
            self._sigr,
            on94_exact,
            illuminate,
        )

    def render(
        self,
        res=300,
        projection="ortho",
        illuminate=True,
        theta=0.0,
        xs=0,
        ys=0,
        zs=1,
        rs=0,
        on94_exact=False,
    ):
        """
        Compute and return the intensity of the map on a grid.

        Returns an image of shape ``(res, res)``, unless ``theta`` is a vector,
        in which case returns an array of shape ``(nframes, res, res)``, where
        ``nframes`` is the number of values of ``theta``. However, if this is
        a spectral map, ``nframes`` is the number of wavelength bins and
        ``theta`` must be a scalar.

        Args:
            res (int, optional): The resolution of the map in pixels on a
                side. Defaults to 300.
            projection (string, optional): The map projection. Accepted
                values are ``ortho``, corresponding to an orthographic
                projection (as seen on the sky), ``rect``, corresponding
                to an equirectangular latitude-longitude projection,
                and ``moll``, corresponding to a Mollweide equal-area
                projection. Defaults to ``ortho``.
            illuminate (bool, optional): Illuminate the map? Default is True.
            theta (scalar or vector, optional): The map rotation phase in
                units of :py:attr:`angle_unit`. If this is a vector, an
                animation is generated. Defaults to ``0.0``.
            xs (scalar or vector, optional): x coordinate of the illumination
                source relative to this body in units of this body's radius.
            ys (scalar or vector, optional): y coordinate of the illumination
                source relative to this body in units of this body's radius.
            zs (scalar or vector, optional): z coordinate of the illumination
                source relative to this body in units of this body's radius.
            rs (scalar, optional): radius of the illumination source in units
                of this body's radius.
        """
        # Multiple frames?
        if self.nw is not None:
            animated = True
        else:
            animated = False
            for arg in [theta, xs, ys, zs]:
                if is_tensor(arg):
                    animated = animated or (
                        hasattr(arg, "ndim") and arg.ndim > 0
                    )
                else:
                    animated = animated or (hasattr(arg, "__len__"))

        # Convert stuff as needed
        projection = get_projection(projection)
        theta = self._math.cast(theta) * self._angle_factor
        xs = self._math.cast(xs)
        ys = self._math.cast(ys)
        zs = self._math.cast(zs)
        Rs = self._math.cast(rs)
        theta, xs, ys, zs = self._math.vectorize(theta, xs, ys, zs)
        illuminate = int(illuminate)
        on94_exact = int(on94_exact)

        # Compute
        if self.nw is None:
            amp = self.amp
        else:
            # The intensity has shape `(nw, res, res)`
            # so we must reshape `amp` to take the product correctly
            amp = self.amp[:, np.newaxis, np.newaxis]

        image = amp * self.ops.render(
            res,
            projection,
            illuminate,
            theta,
            self._inc,
            self._obl,
            self._y,
            self._u,
            self._f,
            xs,
            ys,
            zs,
            Rs,
            self._sigr,
            on94_exact,
        )

        # Squeeze?
        if animated:
            return image
        else:
            return self._math.reshape(image, [res, res])

    def show(self, **kwargs):
        # If the user supplied an image, let's just show it
        if kwargs.get("image", None) is not None:
            return super(ReflectedBase, self).show(**kwargs)

        # Get kwargs
        get_val = evaluator(**kwargs)
        res = kwargs.get("res", 300)
        projection = get_projection(kwargs.get("projection", "ortho"))
        theta = self._math.cast(kwargs.get("theta", 0.0)) * self._angle_factor
        xs = self._math.cast(kwargs.get("xs", 0))
        ys = self._math.cast(kwargs.get("ys", 0))
        zs = self._math.cast(kwargs.get("zs", 1))
        Rs = self._math.cast(kwargs.get("rs", 0))
        theta, xs, ys, zs = self._math.vectorize(theta, xs, ys, zs)
        illuminate = int(kwargs.get("illuminate", True))
        on94_exact = int(kwargs.get("on94_exact", False))
        screen = bool(kwargs.get("screen", True))

        if self.nw is None:
            amp = self.amp
        else:
            # The intensity has shape `(nw, res, res)`
            # so we must reshape `amp` to take the product correctly
            amp = self.amp[:, np.newaxis, np.newaxis]

        # Evaluate the variables
        theta = get_val(theta)
        xs = get_val(xs)
        ys = get_val(ys)
        zs = get_val(zs)
        Rs = get_val(Rs)
        inc = get_val(self._inc)
        obl = get_val(self._obl)
        y = get_val(self._y)
        u = get_val(self._u)
        f = get_val(self._f)
        sigr = get_val(self._sigr)
        amp = get_val(amp)

        if screen and illuminate:

            # Explicitly call the compiled version of `render`
            # on the *unilluminated* map
            kwargs["image"] = amp * self.ops.render(
                res,
                projection,
                0,
                theta,
                inc,
                obl,
                y,
                u,
                f,
                xs,
                ys,
                zs,
                Rs,
                sigr,
                on94_exact,
            )

            # Now call it on an illuminated uniform map
            # We'll use this as an alpha filter.
            illum = self.ops.render(
                res,
                projection,
                1,
                theta,
                inc,
                obl,
                np.append([1.0], np.zeros(self.Ny - 1)),
                u,
                f,
                xs,
                ys,
                zs,
                Rs,
                sigr,
                on94_exact,
            )
            if np.nanmax(illum) > 0:
                illum /= np.nanmax(illum)
            kwargs["overlay"] = illum

        else:

            # Explicitly call the compiled version of `render`
            kwargs["image"] = amp * self.ops.render(
                res,
                projection,
                illuminate,
                theta,
                inc,
                obl,
                y,
                u,
                f,
                xs,
                ys,
                zs,
                Rs,
                sigr,
                on94_exact,
            )

        kwargs["theta"] = theta / self._angle_factor

        return super(ReflectedBase, self).show(**kwargs)


class OblateAmplitude(Amplitude):
    def __get__(self, instance, owner):
        return instance._amp * instance._norm


class OblateBase(object):
    """The oblate ``starry`` map class.

    This class handles maps of oblate spheroids, such as fast-rotating
    stars and planets or bodies with (moderate) tidal distortion.
    It has all the same attributes and methods as :py:class:`starry.maps.YlmBase`,
    with the additions and modifications listed below.

    .. note::
        Instantiate this class by calling :py:func:`starry.Map` with
        ``oblate`` set to True.
    """

    _ops_class_ = OpsOblate

    # Special handling for the map amplitude
    amp = OblateAmplitude()

    # Constants for Planck law (mks)
    _twohcsq = 1.19104295e-16
    _hcdivkb = 1.43877735e-2

    @property
    def _norm(self):
        # Planck's law normalization
        pnorm = self._twohcsq / self._wav ** 5

        if self.__props__.get("normalized", True):

            # Normalize by the flux from a uniform map
            if self.nw is None:
                uniform_y = np.zeros(self.Ny)
                uniform_y[0] = 1.0
                uniform_y = self._math.cast(uniform_y)
            else:
                uniform_y = np.zeros((self.Ny, self.nw))
                uniform_y[0, :] = 1.0
                uniform_y = self._math.cast(uniform_y)
            flux0 = self.ops.flux(
                self._math.cast([0.0]),  # theta
                self._math.cast([0.0]),  # xo
                self._math.cast([0.0]),  # yo
                self._math.cast([0.0]),  # zo
                self._math.cast(0.0),  # ro
                self._inc,
                self._obl,
                self.fproj,
                uniform_y,
                self._u,
                self._f,
            )[0]
            return pnorm / self._math.dot(pnorm * flux0, self._amp)

        else:

            # Trivial
            return pnorm

    def render(self, res=300, projection="ortho", theta=0.0):
        # Multiple frames?
        if self.nw is not None:
            animated = True
        else:
            if is_tensor(theta):
                animated = hasattr(theta, "ndim") and theta.ndim > 0
            else:
                animated = hasattr(theta, "__len__")

        # Convert
        projection = get_projection(projection)
        theta = self._math.vectorize(
            self._math.cast(theta) * self._angle_factor
        )

        # Compute
        if self.nw is None or self.lazy:
            amp = self.amp
        else:
            # The intensity has shape `(nw, res, res)`
            # so we must reshape `amp` to take the product correctly
            amp = self.amp[:, np.newaxis, np.newaxis]
        image = amp * self.ops.render(
            res,
            projection,
            theta,
            self._inc,
            self._obl,
            self.fproj,
            self._y,
            self._u,
            self._f,
        )

        # Squeeze?
        if animated:
            return image
        else:
            return self._math.reshape(image, [res, res])

    def _render_greedy(self, **kwargs):
        get_val = evaluator(**kwargs)
        amp = get_val(self.amp).reshape(-1, 1, 1)
        image = self.ops.render(
            kwargs.get("res", 300),
            get_projection(kwargs.get("projection", "ortho")),
            np.atleast_1d(get_val(kwargs.get("theta", 0.0)))
            * self._angle_factor,
            get_val(self._inc),
            get_val(self._obl),
            get_val(self.fproj),
            get_val(self._y),
            get_val(self._u),
            get_val(self._f),
        )
        return amp * image

    def _get_ortho_borders(self, **kwargs):
        get_val = evaluator(**kwargs)
        obl = get_val(self._obl)
        fproj = get_val(self.fproj)
        xp = np.linspace(-1, 1, 10000)
        yp = np.sqrt(1 - xp ** 2)
        xm = xp
        ym = -yp
        xpr = xp * np.cos(obl) - yp * (1 - fproj) * np.sin(obl)
        ypr = xp * np.sin(obl) + yp * (1 - fproj) * np.cos(obl)
        xmr = xm * np.cos(obl) - ym * (1 - fproj) * np.sin(obl)
        ymr = xm * np.sin(obl) + ym * (1 - fproj) * np.cos(obl)
        return xpr, ypr, xmr, ymr

    def _get_ortho_latitude_lines(self, **kwargs):
        get_val = evaluator(**kwargs)
        inc = get_val(self._inc)
        obl = get_val(self._obl)
        fproj = get_val(self.fproj)
        return get_ortho_latitude_lines(inc=inc, obl=obl, fproj=fproj)

    def _get_ortho_longitude_lines(self, i=0, **kwargs):
        get_val = evaluator(**kwargs)
        inc = get_val(self._inc)
        obl = get_val(self._obl)
        fproj = get_val(self.fproj)
        theta = (
            np.atleast_1d(get_val(kwargs.get("theta", 0.0)))
            * self._angle_factor
        )
        return get_ortho_longitude_lines(
            inc=inc, obl=obl, fproj=fproj, theta=theta[i]
        )

    def reset(self, **kwargs):
        self._fobl = self._math.cast(kwargs.get("f", 0.0))
        self._omega = self._math.cast(kwargs.get("omega", 0.0))
        self._tpole = self._math.cast(kwargs.get("tpole", 5800.0))
        self._beta = self._math.cast(kwargs.get("beta", 0.23))
        super(OblateBase, self).reset(**kwargs)
        self._set_grav_dark_filter()

    @property
    def f(self):
        """The oblateness of the spheroid.

        This is the ratio of the difference between the equatorial and
        polar radii to the equatorial radius, and must be in the range
        ``[0, 1)``.
        """
        return self._fobl

    @f.setter
    def f(self, value):
        self._fobl = self._math.cast(value)
        self._set_grav_dark_filter()

    @property
    def omega(self):
        """
        The angular rotational velocity of the body as a fraction of the breakup velocity.

        """
        return self._omega

    @omega.setter
    def omega(self, value):
        self._omega = self._math.cast(value)
        self._set_grav_dark_filter()

    @property
    def fproj(self):
        """The projected oblateness at the current inclination."""
        return 1 - self._math.sqrt(
            1 - self._fobl * (2 - self._fobl) * self._math.sin(self._inc) ** 2
        )

    @property
    def tpole(self):
        """The polar temperature of the star in K."""
        return self._tpole

    @tpole.setter
    def tpole(self, value):
        self._tpole = self._math.cast(value)
        self._set_grav_dark_filter()

    @property
    def beta(self):
        """The von Zeipel law coefficient."""
        return self._beta

    @beta.setter
    def beta(self, value):
        self._beta = self._math.cast(value)
        self._set_grav_dark_filter()

    @property
    def wav(self):
        """
        The wavelength(s) at which the flux is measured in units of ``wav_unit``.

        """
        return self._wav / self._wav_factor

    @wav.setter
    def wav(self, value):
        value = self._math.cast(value) * self._wav_factor
        if self._nw is None:
            assert value.ndim == 0, "Wavelength must be a scalar."
            self._wav = value
        else:
            assert value.ndim == 1, "Wavelength must be a vector."
            self._wav = value * self._math.ones(self._nw)
        self._set_grav_dark_filter()

    def _set_grav_dark_filter(self):
        if self._fdeg > 0:
            self._f = self.ops.compute_grav_dark_filter(
                self._wav / self._hcdivkb,
                self._omega,
                self._fobl,
                self._beta,
                self._tpole,
            )

    def design_matrix(self, **kwargs):
        r"""Compute and return the light curve design matrix :math:`A`.

        This matrix is used to compute the flux :math:`f` from a vector of spherical
        harmonic coefficients :math:`y` and the map amplitude :math:`a`:
        :math:`f = a A y`.

        Args:
            xo (scalar or vector, optional): x coordinate of the occultor
                relative to this body in units of this body's radius.
            yo (scalar or vector, optional): y coordinate of the occultor
                relative to this body in units of this body's radius.
            zo (scalar or vector, optional): z coordinate of the occultor
                relative to this body in units of this body's radius.
            ro (scalar, optional): Radius of the occultor in units of
                this body's radius.
            theta (scalar or vector, optional): Angular phase of the body
                in units of :py:attr:`angle_unit`.
        """
        # The problem isn't quite linear for spectral maps
        self._no_spectral()

        # Orbital kwargs
        theta, xo, yo, zo, ro = self._get_flux_kwargs(kwargs)

        # Compute & return
        return self.ops.X(
            theta,
            xo,
            yo,
            zo,
            ro,
            self._inc,
            self._obl,
            self.fproj,
            self._u,
            self._f,
        )

    def flux(self, **kwargs):
        """
        Compute and return the flux from the map.

        Args:
            xo (scalar or vector, optional): x coordinate of the occultor
                relative to this body in units of this body's radius.
            yo (scalar or vector, optional): y coordinate of the occultor
                relative to this body in units of this body's radius.
            zo (scalar or vector, optional): z coordinate of the occultor
                relative to this body in units of this body's radius.
            ro (scalar, optional): Radius of the occultor in units of
                this body's radius.
            theta (scalar or vector, optional): Angular phase of the body
                in units of :py:attr:`angle_unit`.
            integrated (bool, optional): If True, dots the flux with the
                amplitude. Default False, in which case this returns a
                2d array (wavelength-dependent maps only).
        """
        # Orbital kwargs
        theta, xo, yo, zo, ro = self._get_flux_kwargs(kwargs)

        # Compute & return
        flux = self.ops.flux(
            theta,
            xo,
            yo,
            zo,
            ro,
            self._inc,
            self._obl,
            self.fproj,
            self._y,
            self._u,
            self._f,
        )

        if kwargs.get("integrated", False):
            return self._math.dot(flux, self.amp)
        else:
            return self.amp * flux


def Map(
    ydeg=0,
    udeg=0,
    nw=None,
    rv=False,
    reflected=False,
    oblate=False,
    source_npts=1,
    gdeg=4,
    normalized=True,
    lazy=None,
    **kwargs
):
    """A generic ``starry`` surface map.

    This function is a class factory that returns either
    a :doc:`spherical harmonic map <SphericalHarmonicMap>`,
    a :doc:`limb darkened map <LimbDarkenedMap>`,
    a :doc:`radial velocity map <RadialVelocityMap>`,
    a :doc:`reflected light map <ReflectedLightMap>`, or
    an :doc:`oblate map <OblateMap>`
    depending on the arguments provided by the user. The default is
    a :doc:`spherical harmonic map <SphericalHarmonicMap>`. If ``rv`` is True,
    instantiates a :doc:`radial velocity map <RadialVelocityMap>` map,
    if ``reflected`` is True, instantiates a :doc:`reflected light map
    <ReflectedLightMap>`, or if ``oblate`` is True, instantiates an
    :doc:`oblate map <OblateMap>`. Otherwise, if ``ydeg`` is zero,
    instantiates a :doc:`limb darkened map <LimbDarkenedMap>`.

    Args:
        ydeg (int, optional): Degree of the spherical harmonic map.
            Defaults to 0.
        udeg (int, optional): Degree of the limb darkening filter.
            Defaults to 0.
        gdeg (int, optional): Degree of the gravity darkening filter.
            Defaults to 4. Enabled only if `oblate` is True.
        nw (int, optional): Number of wavelength bins. Defaults to None
            (for monochromatic light curves).
        rv (bool, optional): If True, enable computation of radial velocities
            for modeling the Rossiter-McLaughlin effect. Defaults to False.
        reflected (bool, optional): If True, models light curves in reflected
            light. Defaults to False.
        oblate (bool, optional): If True, models the object as an oblate
            spheroid. Defaults to False.
        normalized (bool, optional): Whether the flux from a uniform map should
            be normalized to unity regardless of the projected oblateness of
            the object (oblate maps only). Default is True. If False, the flux
            from a uniform map is proportional to its projected area, which
            scales as `1 / (1 - fproj)` where `fproj` is the projected
            oblateness.
        source_npts (int, optional): Number of points used to approximate the
            finite illumination source size. Default is 1. Valid only if
            `reflected` is True.
    """
    # Check args
    ydeg = int(ydeg)
    assert ydeg >= 0, "Keyword `ydeg` must be positive."
    udeg = int(udeg)
    assert udeg >= 0, "Keyword `udeg` must be positive."
    if nw is not None:
        nw = int(nw)
        assert nw > 0, "Number of wavelength bins must be positive."
    gdeg = int(gdeg)
    assert gdeg >= 0, "Keyword `gdeg` must be positive."
    source_npts = int(source_npts)
    if source_npts < 1:
        source_npts = 1
    if lazy is None:
        lazy = config.lazy

    # TODO: phase this next warning out
    if source_npts != 1:
        logger.warning(
            "Finite source size is still an experimental feature. "
            "Use it with care."
        )

    # Limb-darkened?
    if (
        (ydeg == 0)
        and (udeg > 0)
        and (rv is False)
        and (reflected is False)
        and (oblate is False)
    ):

        # TODO: Add support for wavelength-dependent limb darkening
        if nw is not None:
            raise NotImplementedError(
                "Multi-wavelength limb-darkened maps are not yet supported."
            )

        Bases = (LimbDarkenedBase, MapBase)
    else:
        Bases = (YlmBase, MapBase)

    # Radial velocity / reflected light / etc?
    if rv:
        Bases = (RVBase,) + Bases
        fdeg = 3
    elif reflected:
        Bases = (ReflectedBase,) + Bases
        fdeg = 0
    elif oblate:
        Bases = (OblateBase,) + Bases
        fdeg = gdeg
    else:
        fdeg = 0

    # Ensure we're not doing a combo
    if np.count_nonzero([rv, reflected, oblate]) > 1:
        raise NotImplementedError(
            "Combinations of `rv`, `reflected`, and `oblate` not yet implemented."
        )

    # Construct the class
    class Map(*Bases):

        # Tags
        __props__ = dict(
            limbdarkened=LimbDarkenedBase in Bases,
            reflected=ReflectedBase in Bases,
            rv=RVBase in Bases,
            oblate=OblateBase in Bases,
            spectral=nw is not None,
            source_npts=source_npts,
            normalized=normalized,
        )

        def __init__(self, *args, **kwargs):
            self._lazy = lazy
            if lazy:
                self._math = math.lazy_math
                self._linalg = math.lazy_linalg
            else:
                self._math = math.greedy_math
                self._linalg = math.greedy_linalg
            super(Map, self).__init__(*args, source_npts=source_npts, **kwargs)

        @property
        def lazy(self):
            """Map evaluation mode -- lazy or greedy?"""
            return self._lazy

    return Map(ydeg, udeg, fdeg, nw, **kwargs)
