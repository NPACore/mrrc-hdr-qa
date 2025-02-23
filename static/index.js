/* eslint "indent": ["error", 2] */

/** Main websocket data parser. Dispatches based on message type
 * :py:func:`mrqart.track_ws` is tracking this client
 * :py:func:`mrqart.monitor_dirs` is sending the update

 * if new :js:func:`add_new_series` and if unseen update :js:func:`updateUIFromState` (via :py:class:`mrqart.GetState`)

 * @param {dict} wsMessage data from websocket
 * @sideffect updates state
 *  dict with 'type' = 'new' (new sequence) or 'update' (next volume of sequence)
 */
function receivedMessage(wsMessage) {
  const data = JSON.parse(wsMessage.data);
  console.log('New message from websocket:', data);

  if (data['type'] == 'new') {
    add_new_series(data["content"]);
  }

  if (data["type"] == "update") {
    console.log("ws msg is update");
    let seq = document.getElementById("stations");
    if (is_fresh_page()) {
      console.warn(
        "websocket update w/o browser state! HTTP fetch to update browser.",
      );
      fetchState();
    }
  }
}

/** Fetch the current scanner state from /state and update UI
 */
function fetchState() {
  fetch("/state")
    .then((response) => response.json())
    .then((data) => {
      console.log("Fetched state:", data);
      console.warn("Updating UI with fetched state...");
      updateUIFromState(data);
    })
    .catch((err) => {
      // will wait for next websockets push. hopefully no error then
      console.error("Error fetching state:", err);
    });
}

/** Update UI with the fetched state
 */
function updateUIFromState(stateData) {
  // Loop through all stations in the fetched state
  for (const [station, msg] of Object.entries(stateData)) {
    console.log(`adding ${station} data`, msg);
    add_new_series(msg["content"]);
  }
}

/** Connects socket to main dispatcher `receivedMessage`
 */
function update_via_ws() {
  const host = "ws://" + location.hostname + ":5000/";
  console.log("WebSocket connecting to:", host);
  const ws = new WebSocket(host);
  ws.addEventListener("message", receivedMessage);
}

/** new dicom data into table
 * will be embeded in collapsable 'details' for a sequence
 * elements styled by main.css such that
 *   *  correct/expect ("conform" class) is small and grayed out
 *   *  errors/unexpected values ("non-conform" class) are big and red
 * used by 'add_new_series()'
 *
 * @return table html element
*/
function mktable(data) {
  const keys = [
    "SequenceType",
    "Phase",
    "PED_major",
    "TR",
    "TE",
    "Matrix",
    "PixelResol",
    "FoV",
    "BWP",
    "BWPPE",
    "FA",
    "TA",
    "iPAT",
    "Shims",
  ];
  let table = "<table>";
  /*Object.entries(data['input']).map(
       ([k,v]) => `<tr><th>${k}</th><td class=` +
                   ((k in data['errors'])?"no-coform":"conform") +
                   `>${v}</td><td>${data['template'][k]}</td></tr>`) +
       */
  let rows = ["<th></th>", "<th>input</th>", "<th>template</th>"];
  for (const k of keys) {
    conf_css = (k in data["errors"]) ? "no-conform" : "conform";
    rows[0] += `<th class=${conf_css}>${k}</th>`;
    rows[1] += `<td class=${conf_css}>${data["input"][k]}</td>`;
    rows[2] += `<td class=${conf_css}>${data["template"][k]}</td>`;
  }
  table += `<tr>${rows[0]}</tr>` +
    `<tr>${rows[1]}</tr>` +
    `<tr>${rows[2]}</tr>`;
  table += "</table>";
  return table;
}

/** have we seen any data?
 */
function is_fresh_page() {
  let seq = document.getElementById("stations");
  return (seq.innerHTML === "waiting for scanner" || seq.innerHTML === "");
}

/** what to do with type=="new" data: a dicom from a new sequence
 * @param data object with keys 'input', 'template', 'errors', and 'conforms'
 *   the 'content' part of websocket (or /state fetch) message
 *   cf. msg['station'] and msg['type']
 *   message built in python by 'monitor_dirs' (WS) or 'GetState' (HTTP)
 *   'input' is dicom hdr.
 *   'template' is the extected values
 *   'errors' enumrate all paramters in input not matching template
 *   'conforms' is true/false. when false, 'errors' should be {}
*/
function add_new_series(data) {
  let el = document.createElement("li");
  el.className = data["conforms"] ? "conform" : "no-conform";

  let dcm_in = data["input"];
  let errors = data["errors"];

  let summary = `<span class=seqnum>${dcm_in["SeriesNumber"]}</span> 
                   <span class=seqname>${dcm_in["SequenceName"]}</span> 
                   <span class=projname>${dcm_in["Project"]}</span>`;

  for (let k of Object.keys(errors)) {
    summary += `<br>${k} should be <b>${errors[k]["expect"]}</b> 
                    but have <i>${errors[k]["have"]}</i>`;
  }

  const details_status = data["conforms"] ? "" : "open";
  let note = `<details ${details_status}>
                   <summary>${summary}</summary>`;

  note += "<br>" + mktable(data) + "</details>";
  el.innerHTML = note;

  // Clear "waiting for scanner" text
  let seq = document.getElementById("stations");
  if (is_fresh_page()) {
    seq.innerHTML = "";
  }

  const station_id = `station-${dcm_in["Station"]}`;
  let station = document.getElementById(station_id);

  if (!station) {
    // Add new station entry
    document.getElementById("select_station").innerHTML +=
      `<option value="${station_id}">${dcm_in["Station"]}</option>`;

    let newStation = document.createElement("ul");
    newStation.id = station_id;
    seq.prepend(newStation);
    station = newStation;
  }

  // browser accumulates sequences it's seen
  // newest is always on top
  station.prepend(el);
}

/** TODO: parse url to set
 */
function select_station() {
  const cur_station = document.getElementById("select_station").value;
  for (el of document.getElementById("stations").children) {
    visibility = (el.id == cur_station || cur_station == "all")
      ? "block"
      : "none";
    el.style.display = visibility;
    console.log(el.id, visibility);
  }
}

/** hidden text box to test sending what would come from websocket
*/
function show_debug() {
  let cur = document.getElementsByClassName("debug")[0].style.display;
  let toggled = cur === "block" ? "none" : "block";
  document.getElementsByClassName("debug")[0].style.display = toggled;
}
function simdata() {
  let data = document.getElementById("debug");
  data = JSON.parse(data.value);
  add_new_series(data);
}
