// Google Apps Script: Paste this into Google Sheets (Extensions > Apps Script)
// Set up an "onEdit" trigger under Triggers (alarm icon) on the left sidebar.

function onSheetEdit(e) {
  // 1. Create a GitHub Personal Access Token (PAT) with 'repo' scope at:
  //    https://github.com/settings/tokens
  // 2. Paste your token below:
  var GITHUB_TOKEN = "YOUR_GITHUB_PAT_HERE";
  
  // 3. Update with your GitHub username and repository name:
  var REPO_OWNER = "Hashimk101"; 
  var REPO_NAME = "FAST_TimeTable";

  var url = "https://api.github.com/repos/" + REPO_OWNER + "/" + REPO_NAME + "/dispatches";

  var payload = JSON.stringify({
    "event_type": "sheet_updated"
  });

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

  try {
    var response = UrlFetchApp.fetch(url, options);
    Logger.log("GitHub Dispatch Triggered. Response code: " + response.getResponseCode());
  } catch (err) {
    Logger.log("Error dispatching event to GitHub: " + err.toString());
  }
}
