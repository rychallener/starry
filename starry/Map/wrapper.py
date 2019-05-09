# -*- coding: utf-8 -*-
from .bases import *
from .. import modules


__all__ = ["Map"]


def import_by_name(name):
    """Import a module by name."""
    name = "_starry_" + name
    try:
        exec("from ..%s import Map as CBase" % name, globals())
    except ModuleNotFoundError:
        bit = modules[(name + "_").upper()]
        raise ModuleNotFoundError("Requested module not found. " + 
            "Please re-compile `starry` with bit %d enabled." % bit)


def Map(ydeg=0, udeg=0, fdeg=0, **kwargs):
    """
    A wrapper that figures out which `Map` class the user 
    wants and instantiates it.

    """
    # Figure out the correct base class
    multi = kwargs.pop('multi', False)
    reflected = kwargs.pop('reflected', False)
    nw = kwargs.pop('nw', None)
    spectral = (nw is not None)
    nt = kwargs.pop('nt', None)
    temporal = (nt is not None)
    doppler = kwargs.pop('doppler', False)

    if doppler:
        assert reflected is False, \
            "Doppler maps are not implemented in reflected light."
        limbdarkened = False
        kwargs["ydeg"] = ydeg
        kwargs["udeg"] = udeg
        kwargs["fdeg"] = 3
    elif (ydeg == 0) and (fdeg == 0) and (udeg > 0):
        limbdarkened = True
        kwargs["udeg"] = udeg
    else:
        limbdarkened = False
        kwargs["ydeg"] = ydeg
        kwargs["udeg"] = udeg
        kwargs["fdeg"] = fdeg

    # Disallowed combinations
    if limbdarkened and temporal:
        raise NotImplementedError("Pure limb darkening is not implemented " + 
                                  "for temporal maps.")
    elif limbdarkened and reflected:
        raise NotImplementedError("Pure limb darkening is not implemented " + 
                                  "in reflected light.") 
    elif spectral and temporal:
        raise NotImplementedError("Spectral maps cannot have time dependence.")

    # Figure out the module flags
    if spectral:
        kind = "spectral"
        kwargs["nterms"] = nw
    elif temporal:
        kind = "temporal"
        kwargs["nterms"] = nt
    else:
        kind = "default"
    if limbdarkened:
        flag = "ld"
    elif reflected:
        flag = "reflected"
    else:
        flag = "ylm"
    if multi:
        dtype = "multi"
    else:
        dtype = "double"

    # Import it
    import_by_name('%s_%s_%s' % (kind, flag, dtype))

    # Figure out the base classes
    bases = (CBase,)
    if doppler:
        bases = (DopplerBase, YlmBase,) + bases
    elif limbdarkened:
        bases = (LimbDarkenedBase,) + bases
    else:
        bases = (YlmBase,) + bases
        if (fdeg > 0):
            bases = (FilterBase,) + bases

    # Subclass it
    class Map(*bases):
        __doc__ = "".join([base.__doc__ for base in bases])
        def __init__(self, *init_args, **init_kwargs):
            self._multi = multi
            self._reflected = reflected
            self._temporal = temporal
            self._spectral = spectral
            self._scalar = not (self._temporal or self._spectral)
            self._limbdarkened = limbdarkened
            super(Map, self).__init__(*init_args, **init_kwargs)

    # Return an instance
    return Map(**kwargs)