import pandas as pd
import pytest

from IF_analysis.config import Config
from IF_analysis.markers import objectMarker


class DummyExperiment:
    def __init__(self):
        self.data = {}
        self.fig_path = "."


@pytest.mark.filterwarnings("ignore:No Area Data provided")
def test_closest_distances_are_grouped_by_image_identity():
    exp = DummyExperiment()
    dapi_df = pd.DataFrame([
        {
            "Region": "SCN2",
            "Hemisphere": "LH",
            "ROI": "R2",
            "Animal Name": "AnimalB",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 4,
            "IntDen": 1,
            "Mean": 1,
            "XM": 0.0,
            "YM": 0.0,
            "ZM": 1.0,
            "Colocalisation with GFAP": 40.0,
        },
        {
            "Region": "SCN2",
            "Hemisphere": "LH",
            "ROI": "R1",
            "Animal Name": "AnimalA",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 4,
            "IntDen": 1,
            "Mean": 1,
            "XM": 100.0,
            "YM": 0.0,
            "ZM": 1.0,
            "Colocalisation with GFAP": 40.0,
        },
    ])
    gfap_df = pd.DataFrame([
        {
            "Region": "SCN2",
            "Hemisphere": "LH",
            "ROI": "R1",
            "Animal Name": "AnimalA",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 4,
            "IntDen": 1,
            "Mean": 1,
            "XM": 0.0,
            "YM": 0.0,
            "ZM": 1.0,
            "Colocalisation with DAPI": 40.0,
        },
        {
            "Region": "SCN2",
            "Hemisphere": "LH",
            "ROI": "R2",
            "Animal Name": "AnimalB",
            "Volume (micron^3)": 10,
            "Surface (micron^2)": 4,
            "IntDen": 1,
            "Mean": 1,
            "XM": 101.0,
            "YM": 0.0,
            "ZM": 1.0,
            "Colocalisation with DAPI": 40.0,
        },
    ])

    dapi = objectMarker("DAPI", dapi_df, exp, "blue")
    gfap = objectMarker("GFAP", gfap_df, exp, "red")

    assert "DAPI_VolColoc_GFAP" in dapi.df.columns
    assert "GFAP_VolColoc_DAPI" in gfap.df.columns
    assert "DAPI_ColocGFAP" not in dapi.df.columns
    assert "GFAP_ColocDAPI" not in gfap.df.columns

    dapi.find_closest_distances_between_markers(gfap)

    expected = [101.0 / Config.PIXEL_SIZE, 100.0 / Config.PIXEL_SIZE]
    assert dapi.df["DAPI_DistToClosest_GFAP"].tolist() == pytest.approx(expected)
    assert gfap.df["GFAP_ClosestTo_DAPI"].tolist() == [1.0, 1.0]
    assert gfap.df["GFAP_NumClosestTo_DAPI"].tolist() == [1.0, 1.0]
    assert gfap.df["GFAP_VolNumColoc_DAPI"].tolist() == [1.0, 1.0]
    assert gfap.df["GFAP_NumColoc_DAPI"].tolist() == [1.0, 1.0]
