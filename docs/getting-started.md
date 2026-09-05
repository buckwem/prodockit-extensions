---
icon: lucide/rocket
---

{{ heading_counter_reset(page) }}

# Build your first site

This walkthrough starts with an empty directory and ends with a local Zensical
site using numbered headings and a cross-reference. It also demonstrates
`prodockit.steps`: the procedure you are reading is rendered by that extension.

Complete [section 3.1, Installation preparation](installation.md#installation-preparation)
first, using the empty directory for this site when that section asks you to
choose a project directory. Continue below with that directory's `.venv`
active; the repeated Python installation, environment creation and activation
steps are deliberately kept in section 3.1.

/// steps

//// step | Install prodockit

```bash
python -m pip install prodockit
```

Zensical is a core dependency, so this installs the `zensical` command too.
Confirm both commands are available:

```bash
prodockit --version
zensical --version
```

////

//// step | Create the Zensical project

```bash
zensical new .
```

This creates `zensical.toml` and a starter `docs/` directory without
overwriting unrelated files.

////

//// step | Enable the two extensions

Add these tables at the end of `zensical.toml`:

```toml
[project.markdown_extensions."prodockit.headings"]
[project.markdown_extensions."prodockit.refs"]
```

The quoted table names matter: each dotted extension name must remain one TOML
key. Extensions are independent, so a project can enable only these two.

////

//// step | Add content that uses them

Replace `docs/index.md` with:

```md
# My first document

The detail is in \ref{results}.

## Method

Describe what you did here.

## Results {: #results }

Describe what you found here.
```

`prodockit.headings` numbers the sections. `prodockit.refs` turns
`\ref{results}` into a link containing the current number and title, so it
stays correct if the sections move.

////

//// step | Preview the site

```bash
zensical serve
```

Open the local address printed in the terminal. Zensical rebuilds the preview
when a source file changes; stop it with `Ctrl+C`.

////

///

## Where to go next

Continue with the part of the document workflow you need next:

- Browse the [authoring reference](extensions/headings.md) when you need
  another document feature.
- Read [Generate a PDF](pdf.md#pdf-quick-start) when the website is ready to
  print or submit.
- Follow the [project maintenance cycle](project-maintenance.md) when the
  first site becomes a maintained project, then use the
  [command-line map](command-line.md) to choose a command safely.

!!! note "Previewing these documentation changes"
    From this repository's root, run \index{`zensical serve`} and open the address it
    prints. This page already has `prodockit.steps` enabled and styled.
