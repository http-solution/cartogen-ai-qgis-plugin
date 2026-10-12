CARTOGEN AI rc37 - LIVE TEST
============================
You do NOT need Python or any command line. Follow the 8 steps in order.
Time: about 1 to 2 hours for everything. If you only have 30 minutes, do the
rows marked "START HERE" in the prompts page.

WHAT IS IN THIS FOLDER
  README_FIRST.txt          this page
  1_plugin\                 the plugin to install (a .zip file - do not unzip it)
  2_test_files\             sample data. Open smoke_start.qgz from here
  3_PROMPTS.html            double-click to open in your browser. All the tests
  4_RESULTS.csv             open in Excel. Write your results here
  screenshots\              put your screenshots here
  extras\                   the older, longer test pack (only for later)

STEP 1 - Check you have QGIS 4.2
  Open QGIS. Menu Help > About. It must say 4.2.x. (QGIS 3 will not work.)

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

STEP 4 - Open the test project
  Copy the whole 2_test_files folder to somewhere you can write, for example
  your Documents folder. Do not test inside the unzipped download.
  In QGIS: Project > Open, choose smoke_start.qgz from your copy.
  You must see 7 layers: smoke_image, smoke_dem, smoke_points, smoke_hubs,
  smoke_admin, smoke_zones, smoke_boundary. If one is missing, stop and tell us.

STEP 5 - Show the log and open the assistant
  View > Panels > Log Messages  (keep it visible).
  Click the Cartogen AI button to open its panel.
  Open its Settings, pick your provider (Gemini, OpenRouter or Ollama), keep the
  model on "auto", and enter your key.
  Never paste your key into any note, screenshot or file you send back.

STEP 6 - Run the tests
  Double-click 3_PROMPTS.html. It opens in your browser.
  For each test, from top to bottom:
    a) click COPY, paste into the Cartogen chat, press send (do not reword it)
    b) if a confirmation card appears, read it, then approve
    c) compare what happens with "WHAT YOU SHOULD SEE"
    d) take a screenshot and save it in the screenshots folder, named with the
       test id, for example RC37-N1.png
    e) in 4_RESULTS.csv write in the "result" column one of:
         PASS      it did what is expected
         FAIL      it did something else, crashed, froze, or showed an error
         SKIP      you could not run it (write why in notes)
       and in "notes" write one line of what you saw. For a FAIL copy the
       last red/orange lines of Log Messages (never any key).
  Start a New Chat (button in the panel) before each test unless it says
  "same chat".

STEP 7 - Things that must never happen (always a FAIL)
  - QGIS shows "Not Responding" and does not recover
  - QGIS closes by itself
  - the reply says it finished but nothing appears on the map
  - a red error message with no explanation

STEP 8 - Send back
  Zip these and send them: 4_RESULTS.csv, the screenshots folder.
  Also write: Help version shown in the plugin, QGIS version, your operating
  system, which provider and model, free or paid plan, and whether you were on
  a VPN or proxy.

Thank you. Privacy note: every prompt, and what the assistant reads from the
project, goes to the provider you chose. The sample data is synthetic, so this
is safe. Do not open real or sensitive projects while testing.
