// STANDALONE GOOGLE APPS SCRIPT
// Go to https://script.google.com/ and create a new project.
// Configure Script Properties (Project Settings -> Script Properties):
//   - SYNC_WATCHER_SECRET : Shared secret matching Cloudflare Pages SYNC_WATCHER_SECRET
//   - GITHUB_TOKEN        : GitHub PAT with Actions/Contents repository_dispatch scope
//   - PORTAL_URL          : (optional) defaults to https://fast-faculty-timetable.pages.dev
//   - REPO_OWNER          : (optional) defaults to Hashimk101
//   - REPO_NAME           : (optional) defaults to FAST_TimeTable
// Then run setupTrigger() once!

function checkForUpdates() {
  var props = PropertiesService.getScriptProperties();
  var syncWatcherSecret = (props.getProperty("SYNC_WATCHER_SECRET") || "").trim();
  var githubToken = (props.getProperty("GITHUB_TOKEN") || "").trim();
  var portalUrl = (props.getProperty("PORTAL_URL") || "https://fast-faculty-timetable.pages.dev").replace(/\/+$/, "");
  var repoOwner = (props.getProperty("REPO_OWNER") || "Hashimk101").trim();
  var repoName = (props.getProperty("REPO_NAME") || "FAST_TimeTable").trim();

  // Fail closed if required secrets are missing
  if (!syncWatcherSecret || !githubToken) {
    Logger.log("Missing SYNC_WATCHER_SECRET or GITHUB_TOKEN in Script Properties; aborting fail-closed.");
    return;
  }

  try {
    // 1. Fetch authoritative active semester & Google Sheet target from portal control plane
    var targetUrl = portalUrl + "/api/semesters?action=sync_target";
    var targetResp = UrlFetchApp.fetch(targetUrl, {
      "method": "get",
      "headers": {
        "Authorization": "Bearer " + syncWatcherSecret,
        "Cache-Control": "no-cache"
      },
      "muteHttpExceptions": true
    });

    if (targetResp.getResponseCode() !== 200) {
      Logger.log("Fail closed: sync_target returned HTTP " + targetResp.getResponseCode() + " - " + targetResp.getContentText());
      return;
    }

    var target = JSON.parse(targetResp.getContentText());
    if (!target || !target.id || !target.google_sheet_id) {
      Logger.log("Fail closed: sync_target response missing semester id or google_sheet_id.");
      return;
    }

    if (target.sync_policy !== "AUTO_ENABLED") {
      Logger.log("Auto-sync paused (sync_policy=" + target.sync_policy + ") for semester " + target.id + ". Skipping.");
      return;
    }

    var semesterId = String(target.id).trim();
    var SHEET_ID = String(target.google_sheet_id).trim();
    if (!/^[a-zA-Z0-9_-]{20,128}$/.test(SHEET_ID)) {
      Logger.log("Fail closed: invalid google_sheet_id format received: " + SHEET_ID);
      return;
    }

    // 2. Read values AND background colors across all visible day sheets
    var spreadsheet = SpreadsheetApp.openById(SHEET_ID);
    var sheets = spreadsheet.getSheets();
    var allData = [];
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].isSheetHidden()) {
        continue;
      }
      var sheetName = sheets[i].getName();
      var range = sheets[i].getDataRange();
      var values = range.getValues();
      var backgrounds = range.getBackgrounds();
      allData.push(
        sheetName +
          ":V=" +
          JSON.stringify(values) +
          "|BG=" +
          JSON.stringify(backgrounds)
      );
    }

    var combinedData = allData.join("||");
    var currentHash = Utilities.base64Encode(
      Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, combinedData)
    );

    // 3. Semester-keyed hash comparison (switching active term triggers immediate sync)
    var compositeKey = semesterId + ":" + SHEET_ID + ":" + currentHash;
    var lastSheetKey = props.getProperty("LAST_SHEET_KEY");

    if (compositeKey !== lastSheetKey) {
      Logger.log("Changes detected for " + semesterId + " (" + SHEET_ID + ")! Sending dispatch to GitHub...");

      var dispatchUrl = "https://api.github.com/repos/" + repoOwner + "/" + repoName + "/dispatches";
      var payload = JSON.stringify({ "event_type": "sheet_updated" });
      var options = {
        "method": "post",
        "contentType": "application/json",
        "headers": {
          "Authorization": "Bearer " + githubToken,
          "Accept": "application/vnd.github.v3+json"
        },
        "payload": payload,
        "muteHttpExceptions": true
      };

      var response = UrlFetchApp.fetch(dispatchUrl, options);
      if (response.getResponseCode() >= 200 && response.getResponseCode() < 300) {
        props.setProperty("LAST_SHEET_KEY", compositeKey);
        Logger.log("Successfully triggered GitHub Action for " + semesterId + ".");
      } else {
        Logger.log("GitHub Error (" + response.getResponseCode() + "): " + response.getContentText());
      }
    } else {
      Logger.log("No changes detected for " + semesterId + ". Skipping update.");
    }
  } catch (err) {
    Logger.log("Fail closed on error: " + err.toString());
  }
}

// RUN THIS FUNCTION ONCE MANUALLY TO SET UP THE 1-HOUR TRIGGER
function setupTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }

  ScriptApp.newTrigger("checkForUpdates")
           .timeBased()
           .everyHours(1)
           .create();

  Logger.log("Trigger created successfully! It will now check for updates every 1 hour.");
}
