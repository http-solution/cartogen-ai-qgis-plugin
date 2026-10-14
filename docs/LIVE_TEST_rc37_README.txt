CARTOGEN AI {VERSION} - LIVE TEST
============================
You do NOT need Python or any command line. Follow the 9 steps in order.
Time: about 30 minutes for the rows marked "START HERE"; 3 to 4 hours for all.
Do Part A (what is new) first. Part B (open issues) is the full check that
lets us close the open GitHub issues; it needs the extra data in step 4.

WHAT IS IN THIS FOLDER
  README_FIRST.txt             this page
  1_plugin\                    the plugin to install (a .zip file - do not unzip it)
  2_test_files\                ALL the input data (see step 4). Open smoke_start.qgz
  3_PROMPTS.html               double-click: every test, with a Copy button
  4_RESULTS.csv                open in Excel: write PASS / FAIL / SKIP here
  5_OPEN_ISSUES_COVERAGE.csv   which test rows cover which open GitHub issue
  screenshots\                 one screenshot per test, named with the test id
  evidence\                    the cartogen_evidence folders QGIS writes (step 7)
  logs\                        the log files you save (step 7)
  outputs\                     files the assistant created: PDFs, PNGs, HTML, exports
  extras\                      older, longer test documents (only for later)

UPDATING AN EXISTING INSTALL (read this first if Cartogen AI is already in QGIS)
  Two ways to test. Pick ONE per session and say which in note.txt.
  A) UPDATE IN PLACE - tests the upgrade path real users take (do this once):
     1. Write down the version you have now (Cartogen panel > Help > What's new
        shows "Version ...").
     2. Close every QGIS window except one. Save your project first.
     3. Plugins > Manage and Install Plugins > Install from ZIP, choose the file
        in 1_plugin, click Install Plugin. If QGIS asks to replace the installed
        plugin, say yes. Your provider and key are kept (they live in QGIS's
        own settings and Authentication database, not in the plugin folder).
     4. Close QGIS completely and open it again TWICE.
     5. Check: Help > What's new says "Version 1.16.1"; ONE Cartogen AI toolbar
        button; ONE Cartogen AI entry in the Plugins menu; ONE Cartogen panel
        (View > Panels). Open the Log Messages tab CartogenAI: no red lines.
     6. If you see two buttons, a missing panel or a red error: close QGIS, open
        Settings > User Profiles > Open Active Profile Folder, go to
        python\plugins, delete the Cartogen folder (cartogen_ai_plugin, or
        cartogen-ai in very old installs), open QGIS and install again from the
        zip. Write in note.txt what happened BEFORE you deleted anything.
     Record the result in 4_RESULTS.csv on row OI-224 (PASS if step 5 is all
     true). Then carry on with step 4 below; steps 2 and 3 are not needed.
  B) CLEAN INSTALL - tests a first install: follow steps 1 to 3 below exactly.
  Where the files live: the plugin folder is in the profile's python\plugins
  folder; saved chats and notes live in your QGIS settings and project files.
  Nothing in this bundle changes your own projects. Do not test on real or
  sensitive projects.

STEP 1 - Check you have QGIS 4.2
  Open QGIS. Menu Help > About. It must say 4.2.x. (QGIS 3 will not work.)
  Keep that About text: you send it back (step 9).

STEP 2 - Make a clean QGIS profile
  In QGIS: Settings > User Profiles > New Profile. Name it "cartogen-test".
  QGIS opens a new window with that profile. Do all the next steps in it.
  (If you ever installed an older Cartogen AI: close QGIS, delete the folder
  "cartogen-ai" inside the profile's python\plugins folder, then reopen.)

STEP 3 - Install the plugin
  Plugins > Manage and Install Plugins > Install from ZIP.
  Choose the file inside the 1_plugin folder. Click Install Plugin.
  Close QGIS completely and open it again TWICE (restart two times).
  You should see one Cartogen AI button on the toolbar.

STEP 4 - Copy the test data and open the test project
  Copy the whole 2_test_files folder to somewhere you can write, for example
  your Documents folder. Do not test inside the unzipped download.
  The folder holds every input the tests use:
    smoke_start.qgz      the test project (open this one)
    smoke_data.gpkg      7-layer data used by the project: points, hubs, admin,
                         zones, boundary
    smoke_network.gpkg   NEW: roads (with Geofabrik-style oneway F/T/B and
                         speeds), health facilities (a duplicate name, an empty
                         name, one far away), districts with duplicate names,
                         lon/lat copies of the points and hubs, a U-shaped road.
                         Part B adds these with "Add Vector Layer" (row OI-S1)
    smoke_dem.tif        elevation raster (also used as a stand-in population
                         raster in Part B)
    smoke_image.tif      small image raster
    smoke_inform.csv, smoke_ipc.csv, smoke_unosat.csv, smoke_jiaf_hxl.csv
                         tables for the import tests
    smoke_tables.docx, smoke_tables.pdf   documents for the table-reading tests
    CHECKSUMS_sha256.txt checksums of all of these (to prove nothing changed)
  In QGIS: Project > Open, choose smoke_start.qgz from your copy.
  You must see 7 layers: smoke_image, smoke_dem, smoke_points, smoke_hubs,
  smoke_admin, smoke_zones, smoke_boundary. If one is missing, stop and tell us.

STEP 5 - Open the assistant and the log
  View > Panels > Log Messages  (keep it visible; the tab to watch is CartogenAI).
  Click the Cartogen AI button to open its panel.
  Open its Settings, pick your provider (Gemini, OpenRouter or Ollama), keep the
  model on "auto", and enter your key.
  Never paste your key into any note, screenshot, log or file you send back.
  Rows that say "cloud provider" need Gemini or OpenRouter; Ollama is local.
  Rows that say "internet" need a connection.

STEP 6 - Turn on the recorders (they make a FAIL easy to explain)
  In Cartogen Settings tick:
    [x] Save an evidence folder for each request (testing and review)
    [ ] Record every model request and reply (diagnostics)  - tick this ONLY if
        asked, or for a test that FAILS and you want to repeat it. It stores
        what was sent to the model; the sample data is synthetic, but still
        never send it if you used a real project.
  The evidence folders appear as  cartogen_evidence\<time>_<n>  next to the saved
  project (so save the project first: Project > Save As). Each folder holds the
  question, every tool call with its real arguments and result, how long it
  took, the layers it made, the final reply, a map screenshot and copies of the
  files it wrote.

STEP 7 - Run the tests
  Double-click 3_PROMPTS.html. It opens in your browser.
  For each test, from top to bottom:
    a) click COPY, paste into the Cartogen chat, press send (do not reword it)
    b) if a confirmation card appears, read it, then approve (unless the test
       says to do something else)
    c) compare what happens with "WHAT YOU SHOULD SEE"
    d) save a screenshot in the screenshots folder, named with the test id,
       for example RC40-C1.png
    e) in 4_RESULTS.csv write in the "result" column one of:
         PASS      it did what is expected
         FAIL      it did something else, crashed, froze, or showed an error
         SKIP      you could not run it (write why in notes)
       and in "notes" one line of what you saw. For a FAIL also copy the last
       red/orange lines of Log Messages (never any key).
    f) if the test says "create a file" (PDF, PNG, HTML, export), copy that file
       into the outputs folder, named with the test id.
  Start a New Chat (button in the panel) before each test unless it says
  "same chat".
  SAVING THE LOG: after each Part (or after any FAIL), click inside the
  CartogenAI tab of Log Messages, press Ctrl+A then Ctrl+C, paste into Notepad
  and save as  logs\log_<part or test id>.txt.  Do the same for the "General"
  tab if there is anything red. Also save the QGIS "About" text as
  logs\qgis_about.txt (Help > About > select all > copy).

STEP 8 - Things that must never happen (always a FAIL)
  - QGIS shows "Not Responding" and does not recover
  - QGIS closes by itself
  - the reply says it finished but nothing appears on the map
  - a red error message with no explanation
  - the assistant presents map points, figures or a table that no tool produced

STEP 9 - Send back
  Zip and send ONE zip with: 4_RESULTS.csv, the screenshots folder, the
  evidence folder (copy every cartogen_evidence folder into it), the logs
  folder, the outputs folder, and the saved project smoke_oi.qgz.
  Also write a note.txt with: the Help version shown in the plugin, the QGIS
  version (Help > About), your operating system, which provider and model, free
  or paid plan, whether you were on a VPN or proxy (and if the proxy needs a
  login), and the date.

Thank you. Privacy note: every prompt, and what the assistant reads from the
project, goes to the provider you chose. The sample data is synthetic, so this
is safe. Do not open real or sensitive projects while testing.
