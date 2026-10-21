"""Capture legend evidence alongside ReproFig's ordinary axes artists."""


def capture_figure(figure):
    from reprofig import capture_matplotlib
    from reprofig.render.schema import AnnotationSemantic, MarkSemantic

    manifest = capture_matplotlib(figure)
    legends = [(str(axes.get_gid()), axes.get_legend()) for axes in figure.axes]
    legends.extend(('figure', legend) for legend in figure.legends)
    for index, (axes_id, legend) in enumerate(legends):
        if legend is None or not legend.get_visible():
            continue
        prefix = f'{axes_id}-legend-{index}'
        handles = getattr(legend, 'legend_handles', ())
        for number, handle in enumerate(handles):
            if not handle.get_visible():
                continue
            identity = f'{prefix}-swatch-{number}'
            handle.set_gid(identity)
            bounds = handle.get_window_extent().bounds
            style = {}
            for name in ('facecolor', 'edgecolor', 'hatch', 'color', 'linewidth', 'linestyle', 'marker'):
                getter = getattr(handle, 'get_' + name, None)
                if getter is not None:
                    value = getter()
                    if hasattr(value, 'tolist'):
                        value = value.tolist()
                    style[name] = value
            manifest.marks.append(MarkSemantic(
                mark_id=identity, kind='legend-swatch', axes_id=axes_id,
                geometry={'bounds': [float(value) for value in bounds]},
                coordinate_system='display', role='legend', style=style))
        for number, text in enumerate([*legend.get_texts(), legend.get_title()]):
            if not text.get_visible() or not text.get_text():
                continue
            identity = f'{prefix}-text-{number}'
            text.set_gid(identity)
            manifest.annotations.append(AnnotationSemantic(
                annotation_id=identity, text=text.get_text(), axes_id=axes_id,
                position=tuple(map(float, text.get_position())),
                coordinate_system='display', role='legend'))
    return manifest
