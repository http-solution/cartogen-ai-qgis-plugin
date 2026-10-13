---
description: How to install the Cartogen AI plugin in QGIS 4.2 from the release zip, including the install mistake to avoid and the optional dependencies.
---
Cartogen AI needs **QGIS 4.2 or later** (Qt 6). QGIS 3.x is not supported.

## From the release zip (recommended)

1. Open the [releases page](https://github.com/http-solution/cartogen-ai-qgis-plugin/releases) and download the asset named **`cartogen_ai_v<version>.zip`** from the newest release. Each release also carries `SHA256.txt`; compare your download against it.
2. In QGIS: **Plugins → Manage and Install Plugins… → Install from ZIP**, choose the zip, and install.
3. Enable the plugin if QGIS did not do it for you. A **Cartogen AI** button appears on the toolbar and the panel can be opened from the **Plugins** menu.

<div class="callout danger"><strong>Do not install GitHub's "Source code (zip)"</strong>
QGIS uses the zip's top-level folder name as the plugin's Python module name. GitHub names that folder <code>cartogen-ai-qgis-plugin-&lt;tag&gt;</code>; the dots in the version make it an invalid module name and QGIS fails with <code>ModuleNotFoundError: No module named 'cartogen-ai-qgis-plugin-cartogen-ai-v1'</code>. The release asset built by <code>plugin_upload.py</code> always uses the folder <code>cartogen_ai_plugin</code>.
</div>

### Upgrading from an older install

Releases up to rc24 installed into a folder named `cartogen-ai`. From rc25 the folder is `cartogen_ai_plugin` (the plugin directory requires a valid Python identifier). If an old `cartogen-ai` folder is still in your profile's `python/plugins/` directory, **delete it** before installing, or two copies load. Since rc28 the plugin shows a warning at start-up when it finds one. Restart QGIS after installing.

## From source (development)

1. Copy the repository into your QGIS profile's plugin folder **as `cartogen_ai_plugin`**, for example `%APPDATA%\QGIS\QGIS4\profiles\default\python\plugins\cartogen_ai_plugin` on Windows.
2. Do not name the folder exactly `cartogen_ai`: that would shadow the `cartogen_ai` namespace package under `src/` and break every `cartogen_ai.core` import. Do not put dots in the name either.
3. Restart QGIS, or use the Plugin Reloader plugin.

## Optional dependencies

The core plugin needs only `requests`, which QGIS's Python normally already provides. A few features need extra packages, listed in `requirements.txt`:

| Feature | Packages |
|---|---|
| PDF, Word and Excel attachments | `pypdf`, `python-docx`, `openpyxl`, `pandas`, `pdfplumber` |
| `search_web` | `ddgs` |
| Charts and dashboards | `matplotlib`, `folium` |
| Imagery feature extraction (heavy, one tool) | `ultralytics`, which pulls in `torch`; plus a model checkpoint downloaded on first use |

Install them through the bundled `qpip` plugin dependency (QGIS offers to), or in the OSGeo4W Shell with `python -m pip install -r requirements.txt`. A missing package turns off that one feature with a clear message; it does not break the plugin.

<div class="callout warn"><strong>Install packages with QGIS closed</strong>
Replacing a module QGIS already loaded can fail on Windows with <code>PermissionError: [WinError 5] Access is denied</code> on a locked <code>.pyd</code> file. This is a Windows file-lock issue that no code inside the locked process can work around. Close QGIS, install, then reopen it.
</div>

## Plugin directory

Pre-release builds are published as GitHub release assets. Whether a given build is also listed on plugins.qgis.org is stated in the release notes; the upload is made by the maintainer after the directory's own security scan.

Next: [Quick start](@quick-start).
