from types import SimpleNamespace

import pandas as pd
from PIL import Image

from PyFLASH.plotting import plot_representative_images


def test_plot_representative_images_writes_csv_next_to_saved_plot(tmp_path):
    image_path = tmp_path / "source.png"
    Image.new("RGB", (8, 8), color=(220, 20, 20)).save(image_path)

    source = SimpleNamespace(
        name="Batch",
        representative_path=str(tmp_path / "Representative"),
        representative_image_markers=["DAPI"],
    )
    source.images = pd.DataFrame(
        [
            {
                "Experiment": "Batch",
                "Condition": "Control",
                "AnimalName": "A1",
                "ROI": "R1",
                "Marker": "DAPI",
                "ImageName": "source",
                "ImagePath": str(image_path),
                "Extension": ".png",
            }
        ]
    )
    source.representative_images = pd.DataFrame(
        [
            {
                "SelectionGroup": "Control",
                "Condition": "Control",
                "Experiment": "Batch",
                "AnimalName": "A1",
                "ROI": "R1",
                "RepresentativeMarkers": "DAPI",
                "RepresentativeMarkerKey": "dapi",
                "SelectedAt": "2026-07-09T00:00:00",
            }
        ]
    )

    plot_representative_images(
        source,
        markers=["DAPI"],
        save=True,
        show=False,
        image_backend="pil",
        fast_loading=True,
        preview_max_dim=8,
        progress=False,
        block_by="all",
    )

    out_dir = tmp_path / "Representative" / "Batch" / "DAPI"
    assert (out_dir / "representative_images.svg").exists()
    csv_path = out_dir / "representative_image.csv"
    assert csv_path.exists()

    exported = pd.read_csv(csv_path)
    assert "RepresentativeMarkerKey" not in exported.columns
    assert exported.loc[0, "CopiedImages"] == "DAPI_Control_R1.png"

    plot_representative_images(
        source,
        markers=["DAPI"],
        animal_filter="A1",
        save=True,
        show=False,
        image_backend="pil",
        fast_loading=True,
        preview_max_dim=8,
        progress=False,
        block_by="all",
    )

    filtered_dir = out_dir / "A1"
    assert (filtered_dir / "representative_images.svg").exists()
    assert (filtered_dir / "representative_image.csv").exists()
