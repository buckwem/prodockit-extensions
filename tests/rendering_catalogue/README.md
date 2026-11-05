# Zensical rendering review catalogue

This is a separate Zensical project for the reviewable rendering coverage
tracked by [issue #1051](https://github.com/buckwem/prodockit-extensions/issues/1051).
It is deliberately outside the public documentation project.

Phase 1 establishes the reviewed capability inventory, coverage contract and
catalogue navigation. Phase 2 adds reviewable base Markdown and built-in
Python-Markdown specimens. Phase 3 adds all PyMdown extensions and material
configuration settings listed as natively supported by Zensical. The
implemented phases have semantic checks for the website and complete catalogue
PDF. Later phases extend the catalogue and produce the full review bundle.

Check the catalogue source contract from the repository root:

```bash
python -m pytest tests/test_rendering_catalogue.py -q
```

Build the catalogue website locally:

```bash
cd tests/rendering_catalogue
zensical build --clean --strict
```

The local result is written to `tests/rendering_catalogue/site/` and is not
part of the public manual build.

Build the complete review PDF from the catalogue directory:

```bash
pdk pdf
```

After building both outputs, run the built-output semantic assertions from the
repository root:

```bash
python -m pytest tests/test_rendering_catalogue_built.py -m built -q
```
