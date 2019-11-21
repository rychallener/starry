# -*- coding: utf-8 -*-

from .starry_version import __version__

# Is this a docs run?
try:
    __STARRY_DOCS__
except NameError:
    __STARRY_DOCS__ = False

import os

PACKAGEDIR = os.path.abspath(os.path.dirname(__file__))

# Force double precision
import theano.tensor as tt

tt.config.floatX = "float64"

# Set up the default config
from .configdefaults import Config

config = Config()

# Import the main interface
from . import constants, indices, kepler, maps, sht, plotting
from .maps import Map
from .kepler import Primary, Secondary, System

# Clean up the namespace
del tt
del Config

__all__ = [
    "__version__",
    "constants",
    "indices",
    "kepler",
    "maps",
    "sht",
    "plotting",
    "Map",
    "Primary",
    "Secondary",
    "System",
]
