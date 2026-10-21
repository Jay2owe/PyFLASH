"""Observed sample sizes must retain their exact integer meaning."""
import math
import pytest
from PyFLASH.stats_extra import achieved_power


@pytest.mark.parametrize('first,second', [(10,-1),(10,2.5),(2.5,10),
    (math.nan,10),(math.inf,10),(10,math.nan),(10,math.inf),(True,10),(10,False)])
def test_invalid_observed_counts_are_undefined(first, second):
    assert math.isnan(achieved_power(.5,first,second))


def test_explicit_single_observation_in_second_group_is_not_silently_equal_sized():
    assert 0 < achieved_power(.5,10,1) < achieved_power(.5,10,10)
    assert achieved_power(.5,10,None) == achieved_power(.5,10,10)
    assert achieved_power(.5,10,0) == achieved_power(.5,10,10)
