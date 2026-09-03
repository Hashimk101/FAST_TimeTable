// STANDALONE GOOGLE APPS SCRIPT
// Go to https://script.google.com/ and create a new project.
// Paste this code, add your GitHub token, and run the setup() function once!

function checkForUpdates() {
  // 1. Enter the ID of the university's Google Sheet (from the URL)
  // For example, if URL is docs.google.com/spreadsheets/d/1ZQJqdArlwCS9...
  // The ID is 1ZQJqdArlwCS9...
  var SHEET_ID = "1vlTuotLw34fedME3gNQj09cZw-todVomxAiu5P1wZ6Q"; 
  
  // 2. Your GitHub Settings
  var GITHUB_TOKEN = "YOUR_GITHUB_PAT_HERE";
  var REPO_OWNER = "Hashimk101"; 
  var REPO_NAME = "FAST_TimeTable";

  try {
    // Read the current data from the sheet (this works even on view-only sheets!)
    var spreadsheet = SpreadsheetApp.openById(SHEET_ID);
    
    // Read all visible day sheets to catch any text edits across Monday-Saturday
    var sheets = spreadsheet.getSheets();
    var allData = [];
    for (var i = 0; i < sheets.length; i++) {
      // If the sheet was hidden then no need to read it
      if (sheets[i].isSheetHidden()) {
        continue;
      }
      var sheetName = sheets[i].getName();
      var data = sheets[i].getDataRange().getValues();
      var flatData = data.map(function(row) { return row.join(","); }).join(";");
      allData.push(sheetName + ":" + flatData);
    }
    
    var combinedData = allData.join("||");
    var currentHash = Utilities.base64Encode(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, combinedData));
    
    // Check previous hash stored in properties
    var props = PropertiesService.getScriptProperties();
    var lastHash = props.getProperty("LAST_SHEET_HASH");
    
    if (currentHash !== lastHash) {
      Logger.log("Changes detected! Sending webhook to GitHub...");
      
      var url = "https://api.github.com/repos/" + REPO_OWNER + "/" + REPO_NAME + "/dispatches";
      var payload = JSON.stringify({ "event_type": "sheet_updated" });
      var options = {
        "method": "post",
        "contentType": "application/json",
        "headers": {
          "Authorization": "Bearer " + GITHUB_TOKEN,
          "Accept": "application/vnd.github.v3+json"
        },
        "payload": payload,
        "muteHttpExceptions": true
      };
      
      var response = UrlFetchApp.fetch(url, options);
      
      if (response.getResponseCode() >= 200 && response.getResponseCode() < 300) {
        // Only update the hash if the GitHub action was successfully triggered
        props.setProperty("LAST_SHEET_HASH", currentHash);
        Logger.log("Successfully triggered GitHub Action.");
      } else {
        Logger.log("GitHub Error: " + response.getContentText());
      }
    } else {
      Logger.log("No changes detected. Skipping update.");
    }
    
  } catch (err) {
    Logger.log("Error: " + err.toString());
  }
}

// RUN THIS FUNCTION ONCE MANUALLY TO SET UP THE 5-MINUTE TRIGGER
function setupTrigger() {
  // Delete existing triggers to avoid duplicates
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }
  
  // Create a new trigger to run every 5 minutes
  ScriptApp.newTrigger("checkForUpdates")
           .timeBased()
           .everyMinutes(5)
           .create();
           
  Logger.log("Trigger created successfully! It will now check for updates every 5 minutes.");
}
