"""Group construction keeps complete descriptions and rejects ambiguous plans."""
import pytest
from PyFLASH.conditions import ConditionBuilder,condition,multiCondition


def test_three_component_defaults_use_every_component():
    parts = [condition('Label '+name,name,'#123456',factor)
             for name,factor in [('A','Sex'),('B','Treatment'),('C','Time')]]
    result = multiCondition(parts)
    assert result.name == 'ABC'
    assert result.label == 'Label ALabel BLabel C'
    assert result.factor == ['Sex','Treatment','Time']


@pytest.mark.parametrize('operation',[
    lambda builder: builder.order_by('typo'),
    lambda builder: builder.compare_all_pairs(within_factor='typo'),
    lambda builder: builder.compare_to_control('missing',within_factor='Treatment'),
    lambda builder: builder.compare_to_control('C',within_factor='Treatment'),
])
def test_invalid_crossed_plans_fail_without_changing_source_groups(operation):
    left = ConditionBuilder('Sex').add('Female','F',color='#123456').add('Male','M',color='#654321').build()
    right = ConditionBuilder('Treatment').add('Control','C',color='#123456').add('Drug','D',color='#654321').build()
    with pytest.raises(ValueError):
        operation(ConditionBuilder.cross(left,right)).build()
    assert [c.factor_explanation for c in left] == [None,None]
    assert [c.factor_explanation for c in right] == [None,None]


def test_duplicate_short_names_do_not_create_ambiguous_comparisons():
    with pytest.raises(ValueError,match='unique|duplicate'):
        ConditionBuilder('Sex').add('Female','same').add('Male','same').compare_all_pairs().build()
