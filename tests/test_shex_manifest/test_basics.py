from pyshex.shex_manifest.manifest import Manifest


def test_loader():
    manifest = Manifest("https://www.w3.org/2017/10/bibframe-shex/shex-simple-examples.json")
    me = manifest.entries[0]
    assert me.schemaLabel == 'bibframe book'
    assert me.schemaURL == 'book.shex'
    assert me.dataLabel == 'simple'
    assert me.dataURL == 'book.ttl'
    assert me.queryMap == '<samples9298996>@<Work>'
    assert me.status == 'conformant'
    assert len(manifest.entries) == 9