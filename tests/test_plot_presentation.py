"""Shared display edits preserve scientific coordinates and image values."""
import copy
import numpy as np
import pytest
from matplotlib import pyplot as plt
from PyFLASH.aesthetics import _apply_presentation, get_pyflash_style, pyflash_style_context


def test_display_edits_preserve_every_data_and_image_value():
    figure, axes = plt.subplots(1,2)
    try:
        line, = axes[0].plot([1,2,4],[3,5,9],label='Observed')
        points = axes[0].scatter([1,2],[3,5],label='Subjects')
        axes[0].legend()
        pixels = np.arange(9).reshape(3,3)
        image = axes[1].imshow(pixels,cmap='viridis')
        before = copy.deepcopy((line.get_xydata(),points.get_offsets(),image.get_array(),image.get_cmap().name))
        with pyflash_style_context(presentation={'xlim':[0,6],'ylim':[0,12],'legend':'hide',
                'line_width':4,'font_size':17,'font_family':'DejaVu Sans',
                'series_color':'navy','series_colors':{'Observed':'orange'}}):
            _apply_presentation(figure)
        assert axes[0].get_xlim() == (0,6) and axes[0].get_ylim() == (0,12)
        assert line.get_color() == 'orange' and line.get_linewidth() == 4
        np.testing.assert_array_equal(points.get_facecolors()[0], [0,0,128/255,1])
        assert not axes[0].get_legend().get_visible()
        assert axes[0].xaxis.label.get_fontsize() == 17
        for actual,expected in zip((line.get_xydata(),points.get_offsets(),image.get_array()),before[:3]):
            np.testing.assert_array_equal(actual,expected)
        assert image.get_cmap().name == before[3]
    finally:
        plt.close(figure)


@pytest.mark.parametrize('settings', [{'xlim':[2,1]},{'ylim':[0,float('inf')]},
    {'legend':'unknown'},{'series_color':'invalid color'},{'series_colors':{'a':'invalid color'}},
    {'font_size':0},{'line_width':float('nan')},{'font_family':''},{'unknown':True}])
def test_invalid_display_edits_leave_the_previous_style_intact(settings):
    original = get_pyflash_style()
    with pytest.raises(ValueError):
        with pyflash_style_context(presentation=settings):
            pytest.fail('Invalid appearance was applied.')
    assert get_pyflash_style() == original


def test_presentation_mapping_can_be_cleared_without_hidden_prior_edits():
    with pyflash_style_context(presentation={'legend':'hide','xlim':[1,2]}):
        with pyflash_style_context(presentation={'legend':'show'}):
            assert get_pyflash_style('presentation') == {'legend':'show'}
        with pyflash_style_context(presentation={}):
            assert get_pyflash_style('presentation') == {}


def test_bar_groups_and_figure_legends_follow_the_same_series_colours():
    figure, ax = plt.subplots()
    try:
        bars = ax.bar([1,2],[3,4],label='Control')
        legend = figure.legend()
        with pyflash_style_context(presentation={'series_colors':{'Control':'orange'},'legend':'hide'}):
            _apply_presentation(figure)
        from matplotlib.colors import to_rgba
        assert all(patch.get_facecolor() == to_rgba('orange') for patch in bars.patches)
        assert legend.legend_handles[0].get_facecolor() == to_rgba('orange')
        assert not legend.get_visible()
    finally:
        plt.close(figure)


def test_live_view_display_edits_preserve_the_original_specification_and_peer_view():
    from PyFLASH.ui.appearance import style_live_chart
    source = {'data':{'values':[{'x':1,'y':2}]},'mark':{'type':'circle'},
              'encoding':{'x':{'field':'x','type':'quantitative'},
                          'y':{'field':'y','type':'quantitative'},
                          'color':{'field':'group','type':'nominal','scale':{'domain':['a','b']}}}}
    before = copy.deepcopy(source)
    styled = style_live_chart(source,{'xlim':[0,5],'series_color':'navy','legend':'hide',
                                     'font_size':19,'line_width':3})
    assert source == before
    assert styled['data'] == source['data']
    assert styled['encoding']['x']['field'] == 'x'
    assert styled['encoding']['x']['scale']['domain'] == [0,5]
    assert styled['encoding']['color']['scale']['domain'] == ['a','b']
    assert styled['encoding']['color']['scale']['range'] == ['#000080','#000080']
    assert styled['encoding']['color']['legend'] is None
    assert style_live_chart(source,{}) == before


def test_local_font_edit_reserves_space_without_changing_the_data_height():
    from PyFLASH.ui.appearance import style_live_chart
    source = {'height':600,'padding':{'left':79,'right':26,'top':16,'bottom':125},
              'config':{'axis':{'labelFontSize':13},'axisX':{'minExtent':35,'maxExtent':35}}}
    styled = style_live_chart(source,{'font_size':19})
    assert styled['padding'] == {'left':97,'right':38,'top':19,'bottom':125}
    assert styled['config']['axisX']['minExtent'] == 41
    assert styled['height'] == source['height'] == 600
    assert source['padding']['left'] == 79
