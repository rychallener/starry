# -*- coding: utf-8 -*-
"""
Test the nexsci extension.

"""
import numpy as np
import pandas as pd
import pytest
import starry
import warnings
from starry.extensions import from_nexsci

starry.config.lazy = False


@pytest.mark.xfail
def test_lazy_nexsci_query():
    """Tests if the nexsci query works."""

    # These should run without error
    from_nexsci._retrieve_online_data()

    df = from_nexsci._get_nexsci_data()
    assert isinstance(df, pd.DataFrame)
    df = from_nexsci._fill_data(df)
    assert isinstance(df, pd.DataFrame)


@pytest.mark.xfail
def test_lazy_nexsci_local():
    """Tests if creating a system from the local csv file works"""

    # Pass a nice name
    sys = from_nexsci("Kepler-10")
    assert isinstance(sys, starry.System)
    assert len(sys.secondaries) == 2

    # Pass a planet name
    sys = from_nexsci("Kepler-10b")
    assert isinstance(sys, starry.System)
    assert len(sys.secondaries) == 1

    # Pass a bad name
    sys = from_nexsci("kepler 10")
    assert isinstance(sys, starry.System)

    # Pass a random name
    sys = from_nexsci("random")
    assert isinstance(sys, starry.System)
