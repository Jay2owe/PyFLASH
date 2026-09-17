from PyFLASH import context


def test_context_bundle_contract():
    result = context.read(format="json")
    assert result["ok"]
    assert result["version"] == context.__version__
    assert {row["topic"] for row in result["topics"]} == set(context.topics())


def test_context_search_finds_plotting_topic():
    result = context.search("missing column")
    assert result["ok"]
    assert result["results"]
    assert result["results"][0]["topic"] == "troubleshooting"
